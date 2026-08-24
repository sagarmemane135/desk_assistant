# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json
import re
from datetime import date, datetime

import frappe
from frappe.desk.query_report import run as run_query_report
from frappe.utils import getdate

from desk_assistant.tools.guard import max_rows

FINANCIAL_MARKERS = (
	"profit and loss",
	"profit & loss",
	"balance sheet",
	"cash flow",
	"consolidated financial",
)
TRIAL_BALANCE_MARKERS = ("trial balance",)
GENERAL_LEDGER_MARKERS = ("general ledger",)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
SUMMARY_RE = re.compile(
	r"\b(total|net|profit|loss|ebitda|ebit|income|expense|operating)\b",
	re.I,
)
PERIODS = {
	"yearly": "Yearly",
	"year": "Yearly",
	"annual": "Yearly",
	"quarterly": "Quarterly",
	"quarter": "Quarterly",
	"monthly": "Monthly",
	"month": "Monthly",
	"half-yearly": "Half-Yearly",
	"half_yearly": "Half-Yearly",
	"half yearly": "Half-Yearly",
}
FILTER_BASED_ON = {
	"fiscal year": "Fiscal Year",
	"fiscal_year": "Fiscal Year",
	"fy": "Fiscal Year",
	"year": "Fiscal Year",
	"date range": "Date Range",
	"date_range": "Date Range",
	"dates": "Date Range",
	"date": "Date Range",
}
KEY_ALIASES = {
	"from_date": "from_date",
	"fromdate": "from_date",
	"start_date": "from_date",
	"startdate": "from_date",
	"period_start_date": "period_start_date",
	"periodstartdate": "period_start_date",
	"to_date": "to_date",
	"todate": "to_date",
	"end_date": "to_date",
	"enddate": "to_date",
	"period_end_date": "period_end_date",
	"periodenddate": "period_end_date",
	"from_fiscal_year": "from_fiscal_year",
	"fromfiscalyear": "from_fiscal_year",
	"start_year": "from_fiscal_year",
	"startyear": "from_fiscal_year",
	"to_fiscal_year": "to_fiscal_year",
	"tofiscalyear": "to_fiscal_year",
	"end_year": "to_fiscal_year",
	"endyear": "to_fiscal_year",
	"fiscal_year": "fiscal_year",
	"fiscalyear": "fiscal_year",
	"fy": "fiscal_year",
	"year": "fiscal_year",
	"company": "company",
	"filter_based_on": "filter_based_on",
	"filterbasedon": "filter_based_on",
	"periodicity": "periodicity",
	"period": "periodicity",
	"selected_view": "selected_view",
	"selectedview": "selected_view",
	"accumulated_values": "accumulated_values",
	"include_default_book_entries": "include_default_book_entries",
}
FLAT_KEYS = (
	"company",
	"from_date",
	"to_date",
	"period_start_date",
	"period_end_date",
	"from_fiscal_year",
	"to_fiscal_year",
	"fiscal_year",
	"filter_based_on",
	"periodicity",
	"selected_view",
)


def run(args: dict) -> dict:
	report = (args.get("report") or args.get("report_name") or "").strip()
	if not report:
		return {"error": "invalid", "message": "Set a report name."}
	if not frappe.db.exists("Report", report):
		return {"error": "not_found", "report": report}
	denied = _report_denied(report)
	if denied:
		return denied
	filters = normalize_filters(report, args.get("filters"), args)
	try:
		result = run_query_report(
			report_name=report,
			filters=filters,
			ignore_prepared_report=True,
			are_default_filters=False,
		)
	except frappe.PermissionError:
		frappe.clear_messages()
		return {
			"error": "permission_denied",
			"report": report,
			"filters_used": filters,
			"message": "No permission to run this report. Do not invent totals; use query on a readable DocType.",
		}
	except Exception as exc:
		frappe.clear_messages()
		return {
			"error": "report_failed",
			"report": report,
			"filters_used": filters,
			"message": str(exc)[:240],
			"hint": _hint(report),
		}
	columns = result.get("columns") or []
	data = result.get("result") or result.get("data") or []
	rows = [_slim_row(row) for row in data]
	limit = min(len(rows), max_rows())
	picked = _prefer_summary_rows(rows, limit)
	payload = {
		"report": report,
		"columns": _column_labels(columns)[:40],
		"rows": picked,
		"truncated": len(rows) > limit,
		"filters_used": filters,
	}
	if payload["truncated"]:
		payload["note"] = (
			"Showing a subset of report rows (totals first). "
			"For every account balance run Trial Balance; for one ledger run General Ledger."
		)
	return payload


def normalize_filters(report: str, raw=None, args: dict | None = None) -> dict:
	"""Map common aliases so P&L/GL/Trial Balance get the keys ERPNext expects."""
	filters = _coerce_filters(raw)
	for key in FLAT_KEYS:
		value = (args or {}).get(key)
		if value not in (None, "") and key not in filters:
			filters[key] = value
	name = (report or "").lower()
	if _matches(name, FINANCIAL_MARKERS):
		return _fill_financial(filters)
	if _matches(name, TRIAL_BALANCE_MARKERS):
		return _fill_trial_balance(filters)
	if _matches(name, GENERAL_LEDGER_MARKERS):
		return _fill_general_ledger(filters)
	_ensure_company(filters)
	_copy_date_aliases(filters)
	return filters


def _hint(report: str) -> str:
	name = (report or "").lower()
	if _matches(name, FINANCIAL_MARKERS):
		return (
			"Profit and Loss / Balance Sheet need company, filter_based_on "
			"('Fiscal Year' or 'Date Range'), from_fiscal_year and to_fiscal_year "
			"(Fiscal Year names like 2026-2027) or period_start_date and period_end_date, "
			"and periodicity Yearly. Do not pass only from_date/to_date."
		)
	if _matches(name, TRIAL_BALANCE_MARKERS):
		return "Trial Balance needs company, fiscal_year, from_date, and to_date."
	if _matches(name, GENERAL_LEDGER_MARKERS):
		return "General Ledger needs company, from_date, and to_date."
	return "Query Company and Fiscal Year, then retry run_report with those values."


def _coerce_filters(raw) -> dict:
	if not raw:
		return {}
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except json.JSONDecodeError:
			return {}
	if not isinstance(raw, dict):
		return {}
	out = {}
	for key, value in raw.items():
		if value in (None, ""):
			continue
		canon = KEY_ALIASES.get(_key(key), _key(key))
		if canon:
			out[canon] = _stringify_date(value)
	return out


def _key(raw) -> str:
	text = str(raw or "").strip().lower()
	text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
	return text


def _stringify_date(value):
	if isinstance(value, datetime):
		return value.date().isoformat()
	if isinstance(value, date):
		return value.isoformat()
	return value


def _matches(name: str, markers: tuple[str, ...]) -> bool:
	return any(marker in name for marker in markers)


def _fill_financial(filters: dict) -> dict:
	_ensure_company(filters)
	fy = _pick_fiscal_year(filters)
	start = filters.get("period_start_date") or filters.get("from_date")
	end = filters.get("period_end_date") or filters.get("to_date")
	if _looks_like_fiscal_year(start) and not fy:
		fy = start
		start = None
		end = None
	based_on = _canonical_based_on(filters.get("filter_based_on"))
	if not based_on:
		if fy:
			based_on = "Fiscal Year"
		elif start and end:
			based_on = "Date Range"
		else:
			fy = fy or _current_fiscal_year()
			based_on = "Fiscal Year" if fy else "Date Range"
	filters["filter_based_on"] = based_on
	if based_on == "Fiscal Year":
		fy = fy or _current_fiscal_year()
		if fy:
			filters["from_fiscal_year"] = filters.get("from_fiscal_year") or fy
			filters["to_fiscal_year"] = filters.get("to_fiscal_year") or fy
			fy_start, fy_end = _fy_dates(fy)
			if fy_start:
				filters.setdefault("period_start_date", fy_start)
				filters.setdefault("from_date", fy_start)
			if fy_end:
				filters.setdefault("period_end_date", fy_end)
				filters.setdefault("to_date", fy_end)
	else:
		if not (start and end):
			fy = fy or _current_fiscal_year()
			fy_start, fy_end = _fy_dates(fy) if fy else (None, None)
			start = start or fy_start
			end = end or fy_end
		if start:
			filters["period_start_date"] = str(start)
			filters["from_date"] = str(start)
		if end:
			filters["period_end_date"] = str(end)
			filters["to_date"] = str(end)
	filters["periodicity"] = _canonical_period(filters.get("periodicity")) or "Yearly"
	filters.setdefault("selected_view", "Report")
	filters.setdefault("include_default_book_entries", 1)
	return filters


def _fill_trial_balance(filters: dict) -> dict:
	_ensure_company(filters)
	_copy_date_aliases(filters)
	fy = _pick_fiscal_year(filters) or _fiscal_year_for_date(filters.get("from_date")) or _current_fiscal_year()
	if fy:
		filters["fiscal_year"] = fy
		start, end = _fy_dates(fy)
		filters.setdefault("from_date", start or filters.get("from_date"))
		filters.setdefault("to_date", end or filters.get("to_date"))
	return filters


def _fill_general_ledger(filters: dict) -> dict:
	_ensure_company(filters)
	_copy_date_aliases(filters)
	if not (filters.get("from_date") and filters.get("to_date")):
		fy = _pick_fiscal_year(filters) or _current_fiscal_year()
		start, end = _fy_dates(fy) if fy else (None, None)
		if start:
			filters.setdefault("from_date", start)
		if end:
			filters.setdefault("to_date", end)
	return filters


def _copy_date_aliases(filters: dict) -> None:
	if filters.get("period_start_date") and not filters.get("from_date"):
		filters["from_date"] = filters["period_start_date"]
	if filters.get("from_date") and not filters.get("period_start_date"):
		filters["period_start_date"] = filters["from_date"]
	if filters.get("period_end_date") and not filters.get("to_date"):
		filters["to_date"] = filters["period_end_date"]
	if filters.get("to_date") and not filters.get("period_end_date"):
		filters["period_end_date"] = filters["to_date"]


def _ensure_company(filters: dict) -> None:
	if filters.get("company"):
		return
	company = _default_company()
	if company:
		filters["company"] = company


def _pick_fiscal_year(filters: dict) -> str | None:
	for key in ("from_fiscal_year", "to_fiscal_year", "fiscal_year"):
		value = filters.get(key)
		if value:
			return str(value)
	return None


def _canonical_based_on(value) -> str | None:
	if not value:
		return None
	return FILTER_BASED_ON.get(str(value).strip().lower(), str(value).strip())


def _canonical_period(value) -> str | None:
	if not value:
		return None
	return PERIODS.get(str(value).strip().lower(), str(value).strip())


def _looks_like_fiscal_year(value) -> bool:
	text = str(value or "").strip()
	if not text or DATE_RE.match(text):
		return False
	return _fy_exists(text)


def _fy_exists(name: str) -> bool:
	if not name or not frappe.db.exists("DocType", "Fiscal Year"):
		return False
	return bool(frappe.db.exists("Fiscal Year", name))


def _fy_dates(name: str | None) -> tuple[str | None, str | None]:
	if not name or not frappe.db.exists("DocType", "Fiscal Year"):
		return None, None
	row = frappe.db.get_value("Fiscal Year", name, ["year_start_date", "year_end_date"], as_dict=True)
	if not row:
		return None, None
	start = _stringify_date(row.get("year_start_date"))
	end = _stringify_date(row.get("year_end_date"))
	return (str(start) if start else None, str(end) if end else None)


def _current_fiscal_year() -> str | None:
	if not frappe.db.exists("DocType", "Fiscal Year"):
		return None
	today = frappe.utils.today()
	try:
		rows = frappe.get_list(
			"Fiscal Year",
			filters={
				"disabled": 0,
				"year_start_date": ["<=", today],
				"year_end_date": [">=", today],
			},
			fields=["name"],
			limit=1,
		)
	except frappe.PermissionError:
		frappe.clear_messages()
		return None
	return rows[0]["name"] if rows else None


def _fiscal_year_for_date(value) -> str | None:
	if not value or not frappe.db.exists("DocType", "Fiscal Year"):
		return None
	try:
		day = getdate(value)
	except Exception:
		return None
	try:
		rows = frappe.get_list(
			"Fiscal Year",
			filters={
				"disabled": 0,
				"year_start_date": ["<=", day],
				"year_end_date": [">=", day],
			},
			fields=["name"],
			limit=1,
		)
	except frappe.PermissionError:
		frappe.clear_messages()
		return None
	return rows[0]["name"] if rows else None


def _default_company() -> str | None:
	if not frappe.db.exists("DocType", "Company"):
		return None
	name = frappe.defaults.get_user_default("Company")
	if name and frappe.db.exists("Company", name):
		return name
	if frappe.db.exists("DocType", "Global Defaults"):
		name = frappe.db.get_single_value("Global Defaults", "default_company")
		if name:
			return name
	try:
		rows = frappe.get_list("Company", fields=["name"], limit=1)
	except frappe.PermissionError:
		frappe.clear_messages()
		return None
	return rows[0]["name"] if rows else None


def _prefer_summary_rows(rows: list, limit: int) -> list:
	if len(rows) <= limit:
		return rows
	preferred = []
	rest = []
	for row in rows:
		if _is_summary_row(row):
			preferred.append(row)
		else:
			rest.append(row)
	out = preferred[:limit]
	if len(out) < limit:
		out.extend(rest[: limit - len(out)])
	return out


def _is_summary_row(row) -> bool:
	if not isinstance(row, dict):
		return False
	indent = row.get("indent")
	if indent in (0, "0"):
		return True
	label = str(row.get("account_name") or row.get("account") or row.get("section_name") or "")
	return bool(SUMMARY_RE.search(label))


def _slim_row(row):
	if not isinstance(row, dict):
		return row
	out = {}
	for key, value in row.items():
		if str(key).startswith("_") or value in (None, ""):
			continue
		if isinstance(value, (dict, list)) and key not in ("account", "account_name"):
			continue
		out[key] = _stringify_date(value) if isinstance(value, (date, datetime)) else value
	return out


def _report_denied(report: str) -> dict | None:
	if not frappe.has_permission("Report", "read", report):
		return {"error": "permission_denied", "report": report}
	try:
		doc = frappe.get_cached_doc("Report", report)
	except frappe.PermissionError:
		frappe.clear_messages()
		return {"error": "permission_denied", "report": report}
	if doc.disabled:
		return {"error": "disabled", "report": report}
	if not doc.is_permitted():
		return {"error": "permission_denied", "report": report}
	ref = doc.ref_doctype
	if ref and not frappe.has_permission(ref, "report"):
		return {
			"error": "permission_denied",
			"report": report,
			"doctype": ref,
			"message": (
				f"No report permission on {ref}. "
				"Do not invent numbers. Use query on a DocType the user can read."
			),
		}
	return None


def _column_labels(columns: list) -> list:
	out = []
	for col in columns:
		if isinstance(col, dict):
			out.append(col.get("label") or col.get("fieldname") or col.get("name"))
		else:
			out.append(str(col))
	return [c for c in out if c]
