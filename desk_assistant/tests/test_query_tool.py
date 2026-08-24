# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from desk_assistant.providers.base import Completion, LLMConfig
from desk_assistant.tests.users import ensure_user
from desk_assistant.tools import query as query_tool
from desk_assistant.tools.get_doc import run as get_doc_run


class TestQueryTool(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._prev_enabled = frappe.db.get_single_value("AI Assistant Settings", "enabled")
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)

	def tearDown(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("DocType", "AI Assistant Settings"):
			frappe.db.set_single_value("AI Assistant Settings", "enabled", self._prev_enabled)
		super().tearDown()

	def test_user_query_allowed_when_permitted(self):
		out = query_tool.run({"doctype": "User", "fields": ["name", "full_name"], "limit": 1})
		self.assertNotEqual(out.get("error"), "blocked")
		self.assertIn("rows", out)
		self.assertGreaterEqual(len(out["rows"]), 1)
		self.assertNotIn("api_key", frappe.as_json(out))
		self.assertNotIn("password", frappe.as_json(out))

	def test_rejects_user_secret_fields(self):
		out = query_tool.run({"doctype": "User", "fields": ["api_key"], "limit": 1})
		self.assertEqual(out.get("error"), "invalid_field")
		self.assertEqual(out.get("field"), "api_key")

	def test_rejects_sql_comment_and_semicolon(self):
		out = query_tool.run({"doctype": "ToDo", "fields": ["name; drop table tabUser"]})
		self.assertEqual(out.get("error"), "invalid_field")
		out = query_tool.run({"doctype": "ToDo", "fields": ["name--"]})
		self.assertEqual(out.get("error"), "invalid_field")
		out = query_tool.run(
			{"doctype": "ToDo", "fields": ["name"], "filters": [["status;select", "=", "Open"]]}
		)
		self.assertEqual(out.get("error"), "invalid_filter")

	def test_unknown_field_lists_real_columns(self):
		out = query_tool.run({"doctype": "ToDo", "fields": ["is_default"]})
		self.assertEqual(out.get("error"), "invalid_field")
		self.assertIn("suggested_fields", out)
		self.assertIn("description", out["suggested_fields"])

	def test_uses_database_query_without_ignore_permissions(self):
		with patch("desk_assistant.tools.query.DatabaseQuery") as dq:
			inst = dq.return_value
			inst.execute.return_value = [{"name": "TASK-1"}]
			out = query_tool.run({"doctype": "ToDo", "fields": ["name"], "limit": 1})
		dq.assert_called()
		self.assertEqual(dq.call_args[0][0], "ToDo")
		kwargs = inst.execute.call_args.kwargs
		self.assertFalse(kwargs.get("ignore_permissions"))
		self.assertEqual(kwargs.get("user"), frappe.session.user)
		self.assertEqual(kwargs.get("limit"), 2)
		self.assertEqual(out["rows"][0]["name"], "TASK-1")
		self.assertTrue(out["rows"][0]["desk_path"].startswith("/desk/todo/"))

	def test_limit_capped_by_settings(self):
		with (
			patch("desk_assistant.tools.query.max_rows", return_value=5),
			patch("desk_assistant.tools.query.DatabaseQuery") as dq,
		):
			inst = dq.return_value
			inst.execute.return_value = []
			query_tool.run({"doctype": "ToDo", "fields": ["name"], "limit": 100})
		self.assertEqual(inst.execute.call_args.kwargs["limit"], 6)

	def test_blocks_more_secret_doctypes(self):
		for doctype in ("Error Log", "Email Account", "AI Assistant Settings", "User Permission"):
			out = query_tool.run({"doctype": doctype, "fields": ["name"], "limit": 1})
			self.assertEqual(out.get("error"), "blocked", doctype)
			self.assertNotIn("rows", out)

	def test_limited_user_user_query_stays_permission_safe(self):
		email = "da.slice6.noinvoice@example.com"
		ensure_user(email, ["AI Assistant User"])
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user(email)
		out = query_tool.run({"doctype": "User", "fields": ["name"], "limit": 20})
		self.assertNotEqual(out.get("error"), "blocked")
		self.assertNotIn("api_key", frappe.as_json(out))
		self.assertNotIn("password", frappe.as_json(out))
		admin = get_doc_run({"doctype": "User", "name": "Administrator"})
		self.assertIn(admin.get("error"), ("permission_denied", "not_found"))
		self.assertNotIn("doc", admin)

	def test_allowlist_rejects_other_doctypes(self):
		settings = frappe.get_single("AI Assistant Settings")
		before = [row.doc_type for row in (settings.allowed_doctypes or [])]
		settings.set("allowed_doctypes", [])
		settings.append("allowed_doctypes", {"doc_type": "ToDo"})
		settings.save(ignore_permissions=True)
		try:
			ok = query_tool.run({"doctype": "ToDo", "fields": ["name"], "limit": 1})
			self.assertNotEqual(ok.get("error"), "not_allowed")
			denied = query_tool.run({"doctype": "File", "fields": ["name"], "limit": 1})
			self.assertEqual(denied.get("error"), "not_allowed")
			self.assertNotIn("rows", denied)
		finally:
			settings = frappe.get_single("AI Assistant Settings")
			settings.set("allowed_doctypes", [])
			for name in before:
				settings.append("allowed_doctypes", {"doc_type": name})
			settings.save(ignore_permissions=True)

	def test_calendar_2023_sales_invoices_include_desk_path(self):
		if not frappe.db.exists("DocType", "Sales Invoice"):
			self.skipTest("ERPNext Sales Invoice is not installed")
		out = query_tool.run(
			{
				"doctype": "Sales Invoice",
				"fields": ["name", "customer", "grand_total", "posting_date"],
				"filters": [
					["posting_date", "between", ["2023-01-01", "2023-12-31"]],
					["docstatus", "=", 1],
				],
				"order_by": "grand_total desc",
				"limit": 5,
			}
		)
		self.assertNotIn(out.get("error"), ("blocked", "permission_denied"))
		self.assertIn("rows", out)
		self.assertLessEqual(len(out["rows"]), 5)
		for row in out["rows"]:
			self.assertTrue(str(row.get("desk_path") or "").startswith("/desk/"))
			posting = str(row.get("posting_date") or "")
			if posting:
				self.assertTrue(posting.startswith("2023"))

	def test_user_without_sales_invoice_read_gets_permission_denied(self):
		if not frappe.db.exists("DocType", "Sales Invoice"):
			self.skipTest("ERPNext Sales Invoice is not installed")
		email = "da.slice6.noinvoice@example.com"
		ensure_user(email, ["AI Assistant User"])
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)
		frappe.set_user(email)
		self.assertFalse(frappe.has_permission("Sales Invoice", "read"))
		out = query_tool.run(
			{
				"doctype": "Sales Invoice",
				"fields": ["name", "grand_total", "posting_date"],
				"filters": [
					["posting_date", "between", ["2023-01-01", "2023-12-31"]],
					["docstatus", "=", 1],
				],
				"order_by": "grand_total desc",
				"limit": 5,
			}
		)
		self.assertEqual(out.get("error"), "permission_denied")
		self.assertEqual(out.get("doctype"), "Sales Invoice")
		self.assertNotIn("rows", out)
		invoice = frappe.db.get_value("Sales Invoice", {"docstatus": 1}, "name")
		if invoice:
			doc = get_doc_run({"doctype": "Sales Invoice", "name": invoice})
			self.assertEqual(doc.get("error"), "permission_denied")
			self.assertNotIn("doc", doc)

	def test_agent_runs_query_then_answers(self):
		from desk_assistant.agent import run_agent

		cfg = LLMConfig(
			provider="openai",
			model="gpt-4o",
			api_key="sk-test",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)
		first = Completion(
			text="",
			tool_calls=[
				{
					"id": "call_1",
					"name": "query",
					"arguments": {"doctype": "ToDo", "fields": ["name"], "limit": 1},
				}
			],
		)
		second = Completion(text="No open todos.")
		with patch("desk_assistant.agent.complete_chat", side_effect=[first, second]) as complete:
			out = run_agent(cfg, "list todos", system="sys", use_tools=True)
		self.assertEqual(out["text"], "No open todos.")
		self.assertEqual(complete.call_count, 2)
		second_messages = complete.call_args_list[1][0][1]
		roles = [row["role"] for row in second_messages]
		self.assertEqual(roles[-1], "tool")
		self.assertIn("call_1", second_messages[-1]["tool_call_id"])
		self.assertTrue(complete.call_args_list[0].kwargs.get("tools"))

	def test_iter_agent_yields_token_deltas(self):
		from desk_assistant.agent import iter_agent
		from desk_assistant.providers.base import Completion, LLMConfig

		cfg = LLMConfig(
			provider="openai",
			model="gpt-4o",
			api_key="sk-test",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)

		def fake_iter(*args, **kwargs):
			yield "Hel"
			yield "lo "
			yield "there"
			yield Completion(text="Hello there")

		with (
			patch("desk_assistant.agent.complete_chat") as non_stream,
			patch("desk_assistant.agent.complete_chat_iter", side_effect=lambda *a, **k: fake_iter()),
		):
			events = list(iter_agent(cfg, "hi", "sys", use_tools=True, stream=True))
		non_stream.assert_not_called()
		deltas = [e["text"] for e in events if e.get("type") == "delta"]
		self.assertEqual(deltas, ["Hel", "lo ", "there"])
		self.assertEqual(events[-1]["type"], "done")
		self.assertEqual(events[-1]["result"]["text"], "Hello there")
