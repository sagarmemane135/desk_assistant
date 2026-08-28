# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from desk_assistant.permissions import user_is_assistant_manager


class AIChatSession(Document):
	def validate(self):
		if not self.user:
			self.user = frappe.session.user
		if not user_is_assistant_manager() and self.user != frappe.session.user:
			frappe.throw(_("You can only access your own chat sessions."))
		if not self.title and self.messages:
			first = (self.messages[0].content or "").strip().split("\n")[0]
			self.title = first[:80] if first else "Chat"
		self._reject_history_edits()

	def _reject_history_edits(self):
		if self.is_new() or self.flags.allow_message_write:
			return
		before = self.get_doc_before_save()
		if not before:
			return
		if self.user != before.user:
			frappe.throw(_("Chat session user cannot be changed."))
		if self.provider != before.provider or self.model != before.model:
			frappe.throw(_("Provider and model are set by the assistant and cannot be edited."))
		if _message_rows(self) != _message_rows(before):
			frappe.throw(_("Chat messages, tool calls, and query payloads cannot be edited."))


def _message_rows(doc) -> list[tuple]:
	rows = []
	for row in doc.messages or []:
		payload = row.tool_payload
		if payload is None:
			payload_s = ""
		elif isinstance(payload, str):
			payload_s = payload
		else:
			payload_s = frappe.as_json(payload)
		rows.append((row.role or "", row.content or "", row.tool_name or "", payload_s))
	return rows
