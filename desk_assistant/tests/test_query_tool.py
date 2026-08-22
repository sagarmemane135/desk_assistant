# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from desk_assistant.providers.base import Completion, LLMConfig
from desk_assistant.tools import query as query_tool


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

	def test_blocks_user_doctype(self):
		out = query_tool.run({"doctype": "User", "fields": ["name"], "limit": 1})
		self.assertEqual(out.get("error"), "blocked")
		self.assertNotIn("rows", out)

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
