# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from urllib.parse import quote

import frappe
from frappe.desk.utils import slug

from desk_assistant.utils.security import is_blocked_doctype, is_doctype_tool_allowed


def guard_doctype(doctype: str, ptype: str = "read") -> dict | None:
	"""Return an error payload, or None if the user may use this DocType in tools."""
	doctype = (doctype or "").strip()
	if not doctype:
		return {"error": "invalid", "message": "Set a DocType."}
	if not frappe.db.exists("DocType", doctype):
		return {"error": "not_found", "doctype": doctype}
	if is_blocked_doctype(doctype):
		return {"error": "blocked", "doctype": doctype}
	if not is_doctype_tool_allowed(doctype):
		return {"error": "not_allowed", "doctype": doctype}
	if not frappe.has_permission(doctype, ptype):
		return {"error": "permission_denied", "doctype": doctype}
	return None


def desk_path(doctype: str, name: str) -> str:
	return f"/desk/{quote(slug(doctype))}/{quote(str(name))}"


def max_rows() -> int:
	if not frappe.db.exists("DocType", "AI Assistant Settings"):
		return 50
	return max(1, min(200, int(frappe.db.get_single_value("AI Assistant Settings", "max_rows") or 50)))


def max_tool_rounds() -> int:
	if not frappe.db.exists("DocType", "AI Assistant Settings"):
		return 8
	return max(1, min(16, int(frappe.db.get_single_value("AI Assistant Settings", "max_tool_rounds") or 8)))
