# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint

from desk_assistant.security import SECRET_FIELDNAMES
from desk_assistant.tools.guard import desk_path, guard_doctype

PASSWORD_TYPES = frozenset({"Password"})


def run(args: dict) -> dict:
	doctype = (args.get("doctype") or "").strip()
	name = (args.get("name") or "").strip()
	err = guard_doctype(doctype)
	if err:
		return err
	if not name:
		return {"error": "invalid", "message": "Set a document name."}
	try:
		if not frappe.has_permission(doctype, ptype="read", doc=name):
			return {"error": "permission_denied", "doctype": doctype, "name": name}
		doc = frappe.get_doc(doctype, name)
	except frappe.DoesNotExistError:
		frappe.clear_messages()
		return {"error": "not_found", "doctype": doctype, "name": name}
	except frappe.PermissionError:
		frappe.clear_messages()
		return {"error": "permission_denied", "doctype": doctype, "name": name}
	data = strip_secrets(doc.as_dict())
	data["desk_path"] = desk_path(doctype, name)
	return {"doctype": doctype, "name": name, "doc": data}


def strip_secrets(data: dict) -> dict:
	doctype = data.get("doctype")
	if not doctype or not isinstance(data, dict):
		return data
	for name in SECRET_FIELDNAMES:
		data.pop(name, None)
	meta = frappe.get_meta(doctype)
	for df in meta.fields:
		if df.fieldtype in PASSWORD_TYPES or (cint(df.hidden) and df.fieldtype != "Table"):
			data.pop(df.fieldname, None)
		elif df.fieldtype == "Table" and isinstance(data.get(df.fieldname), list):
			data[df.fieldname] = [
				strip_secrets(row) if isinstance(row, dict) else row for row in data[df.fieldname]
			]
	return data
