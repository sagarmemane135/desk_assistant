# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from desk_assistant.tools.get_doc import run as get_doc_run
from desk_assistant.tools.get_doc import strip_secrets


class TestGetDocStripsPassword(FrappeTestCase):
	def test_strip_secrets_drops_password_and_hidden(self):
		data = {
			"doctype": "Email Account",
			"email_id": "desk@example.com",
			"password": "super-secret-password",
		}
		out = strip_secrets(data)
		self.assertEqual(out.get("email_id"), "desk@example.com")
		self.assertNotIn("password", out)
		self.assertNotIn("super-secret-password", frappe.as_json(out))

	def test_blocked_doctype_is_not_loaded(self):
		out = get_doc_run({"doctype": "User AI Settings", "name": "Administrator"})
		self.assertEqual(out.get("error"), "blocked")
		self.assertNotIn("doc", out)

	def test_get_doc_user_strips_secrets_when_permitted(self):
		out = get_doc_run({"doctype": "User", "name": "Administrator"})
		self.assertNotEqual(out.get("error"), "blocked")
		self.assertIn("doc", out)
		self.assertNotIn("password", out["doc"])
		self.assertNotIn("api_key", out["doc"])
		self.assertNotIn("api_secret", out["doc"])
		self.assertNotIn("password", frappe.as_json(out))

	def test_blocked_email_account_is_not_loaded(self):
		out = get_doc_run({"doctype": "Email Account", "name": "anything"})
		self.assertEqual(out.get("error"), "blocked")
		self.assertNotIn("doc", out)

	def test_permission_denied_without_read(self):
		from desk_assistant.tests.users import ensure_user

		email = "da.slice6.noinvoice@example.com"
		ensure_user(email, ["AI Assistant User"])
		frappe.set_user(email)
		out = get_doc_run({"doctype": "ToDo", "name": "does-not-exist-or-denied"})
		self.assertIn(out.get("error"), ("permission_denied", "not_found"))
		self.assertNotIn("doc", out)

	def test_get_me_is_session_user_only(self):
		from desk_assistant.tools.get_me import run as get_me_run

		frappe.set_user("Administrator")
		out = get_me_run({"name": "Guest"})
		self.assertEqual(out["user"], "Administrator")
		self.assertIn("roles", out)
		self.assertGreater(len(out["roles"]), 0)
		self.assertNotIn("password", out)
		self.assertNotIn("api_key", frappe.as_json(out))
		self.assertTrue(out["desk_path"].startswith("/app/user/"))
