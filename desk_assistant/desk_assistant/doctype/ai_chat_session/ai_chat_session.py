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
