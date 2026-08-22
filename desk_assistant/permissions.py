# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint

ROLE_MANAGER = "AI Assistant Manager"
ROLE_USER = "AI Assistant User"


def user_can_use_assistant(user: str | None = None) -> bool:
	"""True only if Settings.enabled and user has AI Assistant User.

	Administrator has every role in Frappe, so they pass the role check when
	Settings is enabled. Other System Managers still need the User role assigned.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if ROLE_USER not in frappe.get_roles(user):
		return False
	if not frappe.db.exists("DocType", "AI Assistant Settings"):
		return False
	return bool(cint(frappe.db.get_single_value("AI Assistant Settings", "enabled")))


def assert_can_use_assistant(user: str | None = None) -> None:
	if not user_can_use_assistant(user):
		frappe.throw(_("Desk Assistant is not enabled for this user."), frappe.PermissionError)


def user_is_assistant_manager(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	roles = frappe.get_roles(user)
	return ROLE_MANAGER in roles or "System Manager" in roles


def check_app_permission() -> bool:
	"""Show this app on the v15 Apps page for managers and granted users."""
	if frappe.session.user == "Administrator":
		return True
	if frappe.session.user == "Guest":
		return False
	return user_is_assistant_manager() or user_can_use_assistant()


def has_user_ai_settings_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user_is_assistant_manager(user):
		return True
	if ROLE_USER not in frappe.get_roles(user):
		return False
	owner = getattr(doc, "user", None) if doc else None
	if not owner:
		return ptype in ("read", "create")
	return owner == user


def get_user_ai_settings_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user_is_assistant_manager(user):
		return ""
	return f"`tabUser AI Settings`.user = {frappe.db.escape(user)}"


def has_chat_session_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user_is_assistant_manager(user):
		return True
	if ROLE_USER not in frappe.get_roles(user):
		return False
	owner = getattr(doc, "user", None) if doc else None
	if not owner:
		return ptype in ("read", "create")
	return owner == user


def get_chat_session_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user_is_assistant_manager(user):
		return ""
	return f"`tabAI Chat Session`.user = {frappe.db.escape(user)}"
