# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from desk_assistant.providers.base import LLMConfig


class TestSessions(FrappeTestCase):
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

	def test_send_persists_and_passes_history(self):
		from desk_assistant.api.chat import get_open_session, send

		cfg = LLMConfig(
			provider="openai",
			model="gpt-4o",
			api_key="sk-must-not-leak",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)
		with (
			patch("desk_assistant.api.chat.resolve_llm_config", return_value=cfg),
			patch(
				"desk_assistant.api.chat.run_agent",
				return_value={"text": "you have System Manager", "provider": "openai", "model": "gpt-4o"},
			),
		):
			first = send(message="what are my roles")
		self.assertTrue(first.get("session"))
		self.assertNotIn("sk-must-not-leak", frappe.as_json(first))
		session = first["session"]
		doc = frappe.get_doc("AI Chat Session", session)
		self.assertEqual(doc.user, "Administrator")
		roles = [row.role for row in doc.messages]
		self.assertEqual(roles[:2], ["user", "assistant"])

		with (
			patch("desk_assistant.api.chat.resolve_llm_config", return_value=cfg),
			patch(
				"desk_assistant.api.chat.run_agent",
				return_value={"text": "yes", "provider": "openai", "model": "gpt-4o"},
			) as agent,
		):
			second = send(message="am I in System Manager", session=session)
		self.assertEqual(second["session"], session)
		self.assertEqual(second["message"], "yes")
		history = agent.call_args.kwargs.get("history") or []
		self.assertTrue(any(row.get("content") == "what are my roles" for row in history))
		self.assertTrue(any("System Manager" in (row.get("content") or "") for row in history))

		opened = get_open_session()
		self.assertEqual(opened["session"], session)
		self.assertGreaterEqual(len(opened["messages"]), 4)

	def test_resume_closed_session_keeps_history(self):
		from desk_assistant.api.chat import resume_session, send

		cfg = LLMConfig(
			provider="openai",
			model="gpt-4o",
			api_key="sk-test",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)
		with (
			patch("desk_assistant.api.chat.resolve_llm_config", return_value=cfg),
			patch(
				"desk_assistant.api.chat.run_agent",
				return_value={"text": "first reply", "provider": "openai", "model": "gpt-4o"},
			),
		):
			first = send(message="hello old thread")
		session = first["session"]
		frappe.db.set_value("AI Chat Session", session, "status", "Closed")
		opened = resume_session(session=session)
		self.assertEqual(opened["session"], session)
		self.assertEqual(frappe.db.get_value("AI Chat Session", session, "status"), "Open")
		self.assertTrue(any(row["content"] == "hello old thread" for row in opened["messages"]))

		with (
			patch("desk_assistant.api.chat.resolve_llm_config", return_value=cfg),
			patch(
				"desk_assistant.api.chat.run_agent",
				return_value={"text": "still here", "provider": "openai", "model": "gpt-4o"},
			) as agent,
		):
			again = send(message="remember me", session=session)
		self.assertEqual(again["session"], session)
		history = agent.call_args.kwargs.get("history") or []
		self.assertTrue(any("hello old thread" in (row.get("content") or "") for row in history))
		other = [row["content"] for row in history if row.get("role") == "user"]
		self.assertNotIn("what are my roles", other)

	def test_stream_emits_ndjson_and_persists(self):
		import json

		from desk_assistant.api.chat import stream
		from werkzeug.wrappers import Response

		cfg = LLMConfig(
			provider="openai",
			model="gpt-4o",
			api_key="sk-must-not-leak",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)

		def fake_iter(*args, **kwargs):
			yield {"type": "status", "text": "Looking up Desk data…"}
			yield {"type": "delta", "text": "Hel"}
			yield {"type": "delta", "text": "lo"}
			yield {
				"type": "done",
				"result": {
					"text": "Hello",
					"provider": "openai",
					"model": "gpt-4o",
					"tool_rows": [],
				},
			}

		with (
			patch("desk_assistant.api.chat.resolve_llm_config", return_value=cfg),
			patch("desk_assistant.api.chat.iter_agent", side_effect=lambda *a, **k: fake_iter()),
		):
			resp = stream(message="ping")
			self.assertIsInstance(resp, Response)
			self.assertIn("ndjson", resp.mimetype or "")
			body = b"".join(resp.iter_encoded()).decode()
		self.assertNotIn("sk-must-not-leak", body)
		rows = [json.loads(line) for line in body.strip().split("\n") if line.strip()]
		types = [row["type"] for row in rows]
		self.assertEqual(types[0], "session")
		self.assertIn("status", types)
		self.assertEqual(types[-1], "done")
		self.assertEqual(rows[-1]["message"], "Hello")
		session = rows[0]["session"]
		doc = frappe.get_doc("AI Chat Session", session)
		roles = [row.role for row in doc.messages]
		self.assertEqual(roles[-2:], ["user", "assistant"])
		self.assertEqual(doc.messages[-1].content, "Hello")

	def test_tool_writes_audit_log(self):
		from desk_assistant.audit import log_tool

		log_tool(
			None,
			"query",
			{"doctype": "ToDo", "limit": 1},
			{"doctype": "ToDo", "rows": [{"name": "x"}], "truncated": False},
			duration_ms=12,
		)
		name = frappe.db.get_value(
			"AI Assistant Audit Log",
			{"tool_name": "query", "user": "Administrator"},
			"name",
			order_by="creation desc",
		)
		self.assertTrue(name)
		row = frappe.get_doc("AI Assistant Audit Log", name)
		self.assertEqual(row.target_doctype, "ToDo")
		self.assertEqual(row.row_count, 1)
		self.assertNotIn("api_key", frappe.as_json(row.as_dict()))
