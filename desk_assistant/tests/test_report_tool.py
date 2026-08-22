# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from desk_assistant.tools import report as report_tool
from desk_assistant.tools.runner import run_tool


class TestReportTool(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._prev_enabled = frappe.db.get_single_value("AI Assistant Settings", "enabled")
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.clear_messages()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.clear_messages()
		if frappe.db.exists("DocType", "AI Assistant Settings"):
			frappe.db.set_single_value("AI Assistant Settings", "enabled", self._prev_enabled)
		super().tearDown()

	def test_denied_ref_doctype_skips_run_and_has_no_desk_modal(self):
		if not frappe.db.exists("Report", "Sales Analytics"):
			self.skipTest("ERPNext Sales Analytics is not installed")
		real = frappe.has_permission

		def fake(doctype, ptype=None, *args, **kwargs):
			if doctype == "Sales Order" and ptype == "report":
				return False
			return real(doctype, ptype, *args, **kwargs)

		with (
			patch("desk_assistant.tools.report.frappe.has_permission", side_effect=fake),
			patch("desk_assistant.tools.report.run_query_report") as run,
		):
			out = report_tool.run({"report": "Sales Analytics"})
		run.assert_not_called()
		self.assertEqual(out.get("error"), "permission_denied")
		self.assertEqual(out.get("doctype"), "Sales Order")
		self.assertFalse(frappe.local.message_log)

	def test_runner_clears_queued_desk_message(self):
		def noisy(_args):
			frappe.msgprint("You don't have permission to get a report on: Sales Order")
			return {"error": "permission_denied", "report": "Sales Analytics"}

		with patch.dict("desk_assistant.tools.runner.HANDLERS", {"run_report": noisy}):
			out = run_tool("run_report", {"report": "Sales Analytics"})
		self.assertEqual(out.get("error"), "permission_denied")
		self.assertFalse(frappe.local.message_log)
