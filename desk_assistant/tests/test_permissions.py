# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from desk_assistant.boot import get_boot_payload
from desk_assistant.permissions import (
	assert_can_use_assistant,
	has_user_ai_settings_permission,
	user_can_use_assistant,
)
from desk_assistant.tests.users import ensure_user

NO_ROLE = "da.slice6.norole@example.com"
GRANTED = "da.slice6.granted@example.com"
SYS_ONLY = "da.slice6.sysman@example.com"


class TestPermissions(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._prev_enabled = 0
		if frappe.db.exists("DocType", "AI Assistant Settings"):
			self._prev_enabled = frappe.db.get_single_value("AI Assistant Settings", "enabled")

	def tearDown(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("DocType", "AI Assistant Settings"):
			frappe.db.set_single_value("AI Assistant Settings", "enabled", self._prev_enabled)
		super().tearDown()

	def test_guest_cannot_use(self):
		frappe.set_user("Guest")
		self.assertFalse(user_can_use_assistant())
		self.assertFalse(get_boot_payload()["enabled"])

	def test_disabled_settings_blocks_even_administrator(self):
		from desk_assistant.api.chat import get_status, send

		frappe.db.set_single_value("AI Assistant Settings", "enabled", 0)
		frappe.set_user("Administrator")
		self.assertFalse(user_can_use_assistant())
		self.assertFalse(get_status()["enabled"])
		self.assertNotIn("api_key", get_status())
		with self.assertRaises(frappe.PermissionError):
			assert_can_use_assistant()
		with self.assertRaises(frappe.PermissionError):
			send(message="top 5 sales invoices of year 2023")

	def test_enabled_without_assistant_user_role_is_blocked(self):
		from desk_assistant.api.chat import get_status, send

		ensure_user(NO_ROLE, [])
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user(NO_ROLE)
		self.assertFalse(user_can_use_assistant())
		self.assertFalse(get_boot_payload()["enabled"])
		self.assertFalse(get_status()["enabled"])
		with self.assertRaises(frappe.PermissionError):
			send(message="hello")

	def test_system_manager_still_needs_assistant_user_role(self):
		ensure_user(SYS_ONLY, ["System Manager"])
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user(SYS_ONLY)
		self.assertFalse(user_can_use_assistant())
		self.assertFalse(get_boot_payload()["enabled"])

	def test_granted_user_sees_boot_flag_without_api_key_in_payload(self):
		from desk_assistant.api.chat import get_status

		ensure_user(GRANTED, ["AI Assistant User"])
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user(GRANTED)
		self.assertTrue(user_can_use_assistant())
		boot = get_boot_payload()
		self.assertTrue(boot["enabled"])
		self.assertNotIn("api_key", boot)
		status = get_status()
		self.assertTrue(status["enabled"])
		self.assertNotIn("api_key", status)

	def test_user_cannot_read_another_users_ai_settings(self):
		ensure_user(GRANTED, ["AI Assistant User"])
		ensure_user(NO_ROLE, ["AI Assistant User"])
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		if not frappe.db.exists("User AI Settings", GRANTED):
			frappe.get_doc({"doctype": "User AI Settings", "user": GRANTED}).insert(
				ignore_permissions=True
			)
		other = frappe.get_doc("User AI Settings", GRANTED)
		frappe.set_user(NO_ROLE)
		self.assertFalse(has_user_ai_settings_permission(other, "read", NO_ROLE))

	def test_run_tool_disabled_without_grant(self):
		from desk_assistant.tools.runner import run_tool

		frappe.db.set_single_value("AI Assistant Settings", "enabled", 0)
		frappe.set_user("Administrator")
		out = run_tool("query", {"doctype": "ToDo", "fields": ["name"], "limit": 1})
		self.assertEqual(out.get("error"), "not_enabled")

	def test_audit_log_write_denied_even_for_administrator(self):
		from desk_assistant.permissions import has_audit_log_permission

		self.assertFalse(has_audit_log_permission(None, "write", "Administrator"))
		self.assertFalse(has_audit_log_permission(None, "create", "Administrator"))
		self.assertTrue(has_audit_log_permission(None, "read"))
