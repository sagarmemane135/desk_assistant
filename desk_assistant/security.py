# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

"""Hard blocklist and optional Settings allowlist for tools."""

import frappe

BLOCKED_DOCTYPES = frozenset(
	{
		"User",
		"Has Role",
		"DocPerm",
		"User Permission",
		"Password",
		"Password Reset",
		"System Settings",
		"Error Log",
		"Email Account",
		"Connected App",
		"OAuth Client",
		"User AI Settings",
		"User AI Model Profile",
		"AI Assistant Settings",
		"DFP External Storage",
	}
)


def is_blocked_doctype(doctype: str) -> bool:
	return bool(doctype) and doctype in BLOCKED_DOCTYPES


def get_allowlist() -> frozenset[str] | None:
	"""None = no allowlist (all readable minus block). Non-empty frozenset = restrict."""
	if not frappe.db.exists("DocType", "AI Assistant Allowed DocType"):
		return None
	rows = frappe.get_all(
		"AI Assistant Allowed DocType",
		filters={"parenttype": "AI Assistant Settings", "parent": "AI Assistant Settings"},
		pluck="doc_type",
	)
	cleaned = {d for d in rows if d}
	return frozenset(cleaned) if cleaned else None


def is_doctype_tool_allowed(doctype: str) -> bool:
	"""Blocklist + optional allowlist. Caller must still check has_permission(read)."""
	if not doctype or is_blocked_doctype(doctype):
		return False
	allowlist = get_allowlist()
	if allowlist is not None and doctype not in allowlist:
		return False
	return True
