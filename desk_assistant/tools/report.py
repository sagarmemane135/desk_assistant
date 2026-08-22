# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe.desk.query_report import run as run_query_report

from desk_assistant.tools.guard import max_rows


def run(args: dict) -> dict:
	report = (args.get("report") or args.get("report_name") or "").strip()
	if not report:
		return {"error": "invalid", "message": "Set a report name."}
	if not frappe.db.exists("Report", report):
		return {"error": "not_found", "report": report}
	denied = _report_denied(report)
	if denied:
		return denied
	filters = args.get("filters") or {}
	if not isinstance(filters, dict):
		filters = {}
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
			"message": "No permission to run this report. Do not invent totals; use query on a readable DocType.",
		}
	except Exception as exc:
		frappe.clear_messages()
		return {"error": "report_failed", "report": report, "message": str(exc)[:240]}
	columns = result.get("columns") or []
	data = result.get("result") or result.get("data") or []
	limit = min(len(data), max_rows())
	return {
		"report": report,
		"columns": _column_labels(columns)[:40],
		"rows": data[:limit],
		"truncated": len(data) > limit,
	}


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
