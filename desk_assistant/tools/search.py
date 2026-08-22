# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe.desk.search import search_link

from desk_assistant.tools.guard import desk_path, guard_doctype, max_rows


def run(args: dict) -> dict:
	doctype = (args.get("doctype") or "").strip()
	txt = str(args.get("txt") or args.get("query") or "").strip()
	err = guard_doctype(doctype)
	if err:
		return err
	if not txt:
		return {"error": "invalid", "message": "Set a search string."}
	try:
		requested = int(args.get("limit") or 10)
	except (TypeError, ValueError):
		requested = 10
	limit = min(max(1, requested), min(20, max_rows()))
	results = search_link(doctype=doctype, txt=txt, page_length=limit)
	rows = []
	for item in results or []:
		if not isinstance(item, dict):
			continue
		name = item.get("value") or item.get("name") or ""
		if not name:
			continue
		rows.append(
			{
				"name": name,
				"label": item.get("label") or item.get("description") or name,
				"desk_path": desk_path(doctype, name),
			}
		)
	return {"doctype": doctype, "rows": rows}
