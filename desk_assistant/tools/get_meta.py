# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe

from desk_assistant.tools.guard import guard_doctype

SKIP_TYPES = frozenset(
	{"Password", "HTML", "Button", "Fold", "Heading", "Tab Break", "Column Break", "Section Break"}
)


def run(args: dict) -> dict:
	doctype = (args.get("doctype") or "").strip()
	err = guard_doctype(doctype)
	if err:
		return err
	meta = frappe.get_meta(doctype)
	fields = []
	for df in meta.fields:
		if df.fieldtype in SKIP_TYPES:
			continue
		item = {
			"fieldname": df.fieldname,
			"fieldtype": df.fieldtype,
			"label": df.label or df.fieldname,
		}
		if df.fieldtype in ("Link", "Dynamic Link", "Select") and df.options:
			item["options"] = df.options
		fields.append(item)
	return {
		"doctype": doctype,
		"title_field": meta.title_field or "name",
		"is_submittable": bool(meta.is_submittable),
		"fields": fields[:120],
	}
