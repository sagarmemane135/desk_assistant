# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AIAssistantAuditLog(Document):
	def before_save(self):
		if not self.is_new():
			frappe.throw(_("Audit log entries cannot be modified."))
