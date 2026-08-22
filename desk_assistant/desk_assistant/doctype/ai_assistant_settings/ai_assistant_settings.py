# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from desk_assistant.passwords import ignore_blank_or_dummy_password


class AIAssistantSettings(Document):
	def validate(self):
		ignore_blank_or_dummy_password(self, "default_api_key")

	def on_update(self):
		# Grant flag lives in per-user bootinfo; a hard refresh is not enough without this.
		frappe.cache.delete_key("bootinfo")
