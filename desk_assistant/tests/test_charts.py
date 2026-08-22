# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from frappe.tests.utils import FrappeTestCase


class TestChartsPrompt(FrappeTestCase):
	def test_system_prompt_asks_for_chart_fence(self):
		from desk_assistant.api.chat import SYSTEM_PROMPT

		self.assertIn("```chart", SYSTEM_PROMPT)
		self.assertIn('"type":"bar"', SYSTEM_PROMPT)
		self.assertIn("do not invent", SYSTEM_PROMPT.lower())
		self.assertIn("do not add a markdown table unless", SYSTEM_PROMPT.lower())
		self.assertIn("do not add a chart unless", SYSTEM_PROMPT.lower())
		self.assertIn("reply in the language", SYSTEM_PROMPT.lower())
		self.assertIn("marathi", SYSTEM_PROMPT.lower())

	def test_citations_from_query_rows(self):
		from desk_assistant.citations import from_tool_rows

		rows = from_tool_rows(
			[
				{
					"tool_name": "query",
					"tool_payload": {
						"doctype": "Sales Invoice",
						"rows": [
							{
								"name": "ACC-SINV-2026-00004",
								"desk_path": "/desk/sales-invoice/ACC-SINV-2026-00004",
							}
						],
					},
				}
			]
		)
		self.assertEqual(rows[0]["name"], "ACC-SINV-2026-00004")
	def test_detects_speak_in_marathi(self):
		from desk_assistant.language import detect_language, resolve_reply_language

		self.assertIn("Marathi", detect_language("can you speak in marathi") or "")
		self.assertIn("Hindi", detect_language("speak in hindi") or "")
		self.assertEqual(detect_language("can you speak in japanese"), "Japanese")
		self.assertIsNone(detect_language("reply in the table"))
		self.assertIn("Marathi", detect_language("मराठीत बोला") or "")
		self.assertIn(
			"Marathi",
			resolve_reply_language(
				"which customer has the largest overdue?",
				[{"role": "user", "content": "speak in marathi"}],
			)
			or "",
		)
		self.assertIsNone(
			resolve_reply_language(
				"speak in english",
				[{"role": "user", "content": "speak in marathi"}],
			)
		)
