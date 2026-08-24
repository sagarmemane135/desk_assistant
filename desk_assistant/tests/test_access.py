# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint

from desk_assistant.permissions import assert_can_use_assistant, user_can_use_assistant
from desk_assistant.utils.security import is_blocked_doctype, is_doctype_tool_allowed


class TestAccess(FrappeTestCase):
	def setUp(self):
		super().setUp()
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

	def test_disabled_settings_blocks_send(self):
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 0)
		frappe.set_user("Administrator")
		self.assertFalse(user_can_use_assistant())
		with self.assertRaises(frappe.PermissionError):
			assert_can_use_assistant()

	def test_enabled_without_user_role_is_blocked(self):
		from unittest.mock import patch

		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		with patch("desk_assistant.permissions.frappe.get_roles", return_value=["Employee"]):
			self.assertFalse(user_can_use_assistant("someone@example.com"))

	def test_enabled_administrator_can_use(self):
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user("Administrator")
		self.assertTrue(user_can_use_assistant())

	def test_secret_doctypes_stay_blocked(self):
		self.assertFalse(is_blocked_doctype("User"))
		self.assertFalse(is_blocked_doctype("Has Role"))
		self.assertTrue(is_blocked_doctype("User Permission"))
		self.assertTrue(is_blocked_doctype("User AI Settings"))
		self.assertTrue(is_blocked_doctype("User AI Model Profile"))
		self.assertTrue(is_blocked_doctype("AI Assistant Settings"))
		self.assertFalse(is_blocked_doctype("Sales Invoice"))

	def test_empty_allowlist_allows_item(self):
		self.assertTrue(is_doctype_tool_allowed("Item"))
		self.assertTrue(is_doctype_tool_allowed("User"))
		self.assertFalse(is_doctype_tool_allowed("User AI Settings"))

	def test_save_prefs_blocked_when_disabled(self):
		from desk_assistant.api.sidebar import save_prefs

		frappe.db.set_single_value("AI Assistant Settings", "enabled", 0)
		with self.assertRaises(frappe.PermissionError):
			save_prefs(width=400, collapsed=0)

	def test_save_prefs_does_not_bump_modified(self):
		from desk_assistant.api.sidebar import get_or_create_user_settings, save_prefs

		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user("Administrator")
		doc = get_or_create_user_settings()
		before = str(frappe.db.get_value("User AI Settings", doc.name, "modified"))
		next_width = 400 if cint(doc.sidebar_width) != 400 else 401
		out = save_prefs(width=next_width, collapsed=0)
		after = str(frappe.db.get_value("User AI Settings", doc.name, "modified"))
		self.assertEqual(before, after)
		self.assertEqual(out["sidebar_width"], next_width)
		self.assertEqual(cint(frappe.db.get_value("User AI Settings", doc.name, "sidebar_width")), next_width)

	def test_llm_settings_api_omits_key(self):
		from unittest.mock import patch

		from desk_assistant.api.sidebar import get_llm_settings, save_llm_settings

		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user("Administrator")
		with patch("desk_assistant.api.sidebar._password", return_value="sk-hidden"):
			got = get_llm_settings()
		self.assertNotIn("api_key", got)
		self.assertNotIn("sk-hidden", frappe.as_json(got))
		self.assertTrue(got["has_api_key"])
		self.assertIn("active_model", got)
		self.assertIn("profiles", got)

		with patch("desk_assistant.api.sidebar.public_llm_status", return_value={
			"provider": "openai",
			"model": "gpt-4o-mini",
			"has_api_key": True,
		}), patch("desk_assistant.api.sidebar.get_or_create_user_settings") as factory:
			doc = frappe.get_doc({"doctype": "User AI Settings", "user": "Administrator"})
			doc.save = lambda *args, **kwargs: None
			factory.return_value = doc
			out = save_llm_settings(provider="openai", model="gpt-4o-mini", base_url="", api_key="sk-hidden")
		self.assertNotIn("api_key", out)
		self.assertNotIn("sk-hidden", frappe.as_json(out))

	def test_can_save_two_provider_profiles(self):
		from desk_assistant.api.sidebar import delete_profile, get_llm_settings, save_llm_settings

		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user("Administrator")
		before = {row["name"] for row in (get_llm_settings().get("profiles") or [])}
		first = save_llm_settings(
			provider="openai",
			model="gpt-4o-mini",
			base_url="https://api.openai.com/v1",
			as_new=1,
		)
		second = save_llm_settings(
			provider="groq",
			model="llama-3.3-70b-versatile",
			base_url="https://api.groq.com/openai/v1",
			as_new=1,
		)
		names = {row["name"] for row in (second.get("profiles") or [])}
		added = names - before
		self.assertGreaterEqual(len(second.get("profiles") or []), 2)
		self.assertEqual(second["provider"], "groq")
		self.assertEqual(second["model"], "llama-3.3-70b-versatile")
		got = get_llm_settings()
		providers = {row["provider"] for row in got["profiles"]}
		self.assertIn("openai", providers)
		self.assertIn("groq", providers)
		self.assertNotIn("api_key", got)
		for row in got["profiles"]:
			self.assertNotIn("api_key", row)
		for name in added:
			delete_profile(name)
		_ = first

	def test_extend_bootinfo_overwrites_stale_cache(self):
		from desk_assistant.boot import extend_bootinfo

		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user("Administrator")
		bootinfo = frappe._dict({"desk_assistant": {"enabled": False}})
		extend_bootinfo(bootinfo)
		self.assertTrue(bootinfo.desk_assistant["enabled"])
