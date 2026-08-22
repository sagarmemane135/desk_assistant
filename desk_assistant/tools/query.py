# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.db_query import DatabaseQuery

from desk_assistant.tools.guard import desk_path, guard_doctype, max_rows

DANGEROUS = re.compile(r";|--|/\*|\*/|\bunion\b|\bselect\b", re.I)
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
AGG = re.compile(r"^(sum|count|avg|min|max)\(([A-Za-z][A-Za-z0-9_]*)\)$", re.I)
LINKED = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)$")
ORDER = re.compile(
	r"^`?(?:sum|count|avg|min|max)\([A-Za-z][A-Za-z0-9_]*\)`?$|^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)?$",
	re.I,
)


def run(args: dict) -> dict:
	doctype = (args.get("doctype") or "").strip()
	err = guard_doctype(doctype)
	if err:
		return err

	fields = _clean_fields(args.get("fields") or ["name"])
	group_by = _clean_ident(args.get("group_by"))
	checked = _validate_fields(doctype, fields, group_by)
	if checked.get("error"):
		return checked
	fields = checked["fields"]

	limit = min(max(1, _as_int(args.get("limit"), 10)), max_rows())
	filters, ferr = _sanitize_filters(args.get("filters"), "filters")
	if ferr:
		return ferr
	or_filters, oerr = _sanitize_filters(args.get("or_filters"), "or_filters")
	if oerr:
		return oerr
	order_by = _clean_order(args.get("order_by"))

	query = DatabaseQuery(doctype, user=frappe.session.user)
	try:
		rows = query.execute(
			fields=fields,
			filters=filters,
			or_filters=or_filters,
			group_by=group_by,
			order_by=order_by,
			limit=limit + 1,
			ignore_permissions=False,
			user=frappe.session.user,
			as_list=False,
		)
	except frappe.PermissionError:
		frappe.clear_messages()
		return {"error": "permission_denied", "doctype": doctype}
	except Exception as exc:
		frappe.clear_messages()
		return {"error": "query_failed", "doctype": doctype, "message": str(exc)[:240]}
	truncated = len(rows) > limit
	rows = rows[:limit]
	for row in rows:
		if isinstance(row, dict) and row.get("name"):
			row["desk_path"] = desk_path(doctype, row["name"])
	return {"doctype": doctype, "rows": rows, "truncated": truncated}


def _as_int(value, default: int) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _sanitize_filters(filters, label: str):
	if not filters:
		return None, None
	if isinstance(filters, str):
		return None, {"error": "invalid_filter", "message": f"{label} must be a list or object."}
	if isinstance(filters, dict):
		for key in filters:
			if DANGEROUS.search(str(key)) or not (IDENT.match(str(key)) or LINKED.match(str(key))):
				return None, {"error": "invalid_filter", "field": str(key)}
		return filters, None
	if isinstance(filters, list):
		for item in filters:
			field = _filter_field(item)
			if field and DANGEROUS.search(field):
				return None, {"error": "invalid_filter", "field": field}
		return filters, None
	return None, {"error": "invalid_filter", "message": f"{label} must be a list or object."}


def _filter_field(item) -> str | None:
	if isinstance(item, (list, tuple)) and len(item) >= 2:
		if len(item) >= 4 and isinstance(item[0], str) and isinstance(item[1], str):
			return str(item[1])
		return str(item[0])
	return None


def _clean_fields(fields) -> list[str]:
	if isinstance(fields, str):
		fields = [fields]
	out = []
	for raw in fields or []:
		value = str(raw or "").strip().strip("`")
		if value:
			out.append(value)
	return out or ["name"]


def _clean_ident(value) -> str | None:
	value = str(value or "").strip().strip("`")
	if not value:
		return None
	if not IDENT.match(value):
		return None
	return value


def _clean_order(value) -> str | None:
	value = str(value or "").strip()
	if not value:
		return None
	if DANGEROUS.search(value):
		return None
	parts = value.split()
	field = parts[0].strip("`")
	direction = (parts[1] if len(parts) > 1 else "asc").lower()
	if direction not in ("asc", "desc"):
		return None
	if not ORDER.match(field):
		return None
	return f"{field} {direction}"


def _validate_fields(doctype: str, fields: list[str], group_by: str | None) -> dict:
	meta = frappe.get_meta(doctype)
	names = {df.fieldname for df in meta.fields}
	names.update({"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"})
	clean = []
	for field in fields:
		if DANGEROUS.search(field):
			return {"error": "invalid_field", "field": field}
		agg = AGG.match(field)
		if agg:
			if not group_by:
				return {"error": "invalid_field", "field": field, "message": "Aggregates need group_by."}
			inner = agg.group(2)
			if inner != "*" and inner not in names:
				return {"error": "invalid_field", "field": field}
			clean.append(field)
			continue
		linked = LINKED.match(field)
		if linked:
			link_field, target_field = linked.group(1), linked.group(2)
			df = meta.get_field(link_field)
			if not df or df.fieldtype != "Link" or not df.options:
				return {"error": "invalid_field", "field": field}
			target_meta = frappe.get_meta(df.options)
			target_names = {f.fieldname for f in target_meta.fields} | {"name"}
			if target_field not in target_names:
				return {"error": "invalid_field", "field": field}
			clean.append(field)
			continue
		if not IDENT.match(field) or field not in names:
			return _unknown_field(doctype, field)
		clean.append(field)
	return {"fields": clean}


def _unknown_field(doctype: str, field: str) -> dict:
	sample = _suggested_fields(doctype)
	return {
		"error": "invalid_field",
		"field": field,
		"message": f"{field} is not a field on this DocType. Use get_meta or one of: {', '.join(sample)}.",
		"suggested_fields": sample,
	}


def _suggested_fields(doctype: str) -> list[str]:
	skip = {
		"Password",
		"HTML",
		"Button",
		"Fold",
		"Heading",
		"Tab Break",
		"Column Break",
		"Section Break",
	}
	meta = frappe.get_meta(doctype)
	out = ["name"]
	for df in meta.fields:
		if df.fieldtype in skip or not df.fieldname:
			continue
		if df.fieldname not in out:
			out.append(df.fieldname)
	return out[:24]
