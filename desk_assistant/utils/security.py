# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

"""Hard blocklist and optional Settings allowlist for tools."""

import frappe

BLOCKED_DOCTYPES = frozenset(
	{
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

# Always stripped from get_doc / rejected on query, even when the field is not Password.
SECRET_FIELDNAMES = frozenset(
	{
		"api_key",
		"api_secret",
		"password",
		"new_password",
		"reset_password_key",
		"last_reset_password_key",
		"otp_secret",
		"otpsecret",
		"last_password",
	}
)


def is_blocked_doctype(doctype: str) -> bool:
	return bool(doctype) and doctype in BLOCKED_DOCTYPES


def is_secret_field(field: str) -> bool:
	return bool(field) and field in SECRET_FIELDNAMES


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
