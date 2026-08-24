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

	def test_normalize_pl_maps_from_to_date(self):
		from desk_assistant.tools.report import normalize_filters

		out = normalize_filters(
			"Profit and Loss Statement",
			{"From Date": "2026-04-01", "To Date": "2027-03-31", "Company": "Test Company"},
		)
		self.assertEqual(out["company"], "Test Company")
		self.assertEqual(out["filter_based_on"], "Date Range")
		self.assertEqual(out["period_start_date"], "2026-04-01")
		self.assertEqual(out["period_end_date"], "2027-03-31")
		self.assertEqual(out["periodicity"], "Yearly")

	def test_normalize_pl_fiscal_year_name(self):
		from desk_assistant.tools.report import normalize_filters

		out = normalize_filters(
			"Profit and Loss Statement",
			{"fiscal_year": "2026-2027", "company": "Test Company"},
		)
		self.assertEqual(out["filter_based_on"], "Fiscal Year")
		self.assertEqual(out["from_fiscal_year"], "2026-2027")
		self.assertEqual(out["to_fiscal_year"], "2026-2027")
		self.assertEqual(out["periodicity"], "Yearly")

	def test_run_report_passes_normalized_filters(self):
		if not frappe.db.exists("Report", "Profit and Loss Statement"):
			self.skipTest("ERPNext Profit and Loss Statement is not installed")
		captured = {}

		def fake_run(**kwargs):
			captured.update(kwargs)
			return {"columns": [], "result": []}

		with patch("desk_assistant.tools.report.run_query_report", side_effect=fake_run):
			out = report_tool.run(
				{
					"report": "Profit and Loss Statement",
					"filters": {"from_date": "2026-04-01", "to_date": "2027-03-31"},
				}
			)
		self.assertNotEqual(out.get("error"), "report_failed")
		filters = captured.get("filters") or {}
		self.assertEqual(filters.get("filter_based_on"), "Date Range")
		self.assertEqual(filters.get("period_start_date"), "2026-04-01")
		self.assertEqual(filters.get("period_end_date"), "2027-03-31")
		self.assertTrue(filters.get("company"))
		self.assertIn("filters_used", out)
