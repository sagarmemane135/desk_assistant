# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from desk_assistant.permissions import user_is_assistant_manager
from desk_assistant.utils.passwords import ignore_blank_or_dummy_password
from desk_assistant.utils.profiles import profile_label


class UserAISettings(Document):
	def before_naming(self):
		user = (self.user or "").strip()
		if user and frappe.db.exists("User AI Settings", user):
			frappe.throw(
				_(
					"User AI Settings for {0} already exists. Open that document and add another row under Saved providers — each user has only one settings document."
				).format(user)
			)

	def validate(self):
		if not self.user:
			self.user = frappe.session.user
		if not user_is_assistant_manager() and self.user != frappe.session.user:
			frappe.throw(_("You can only manage your own AI settings."))
		ignore_blank_or_dummy_password(self, "api_key")
		for row in self.get("profiles") or []:
			ignore_blank_or_dummy_password(row, "api_key")
			if not (row.profile_name or "").strip():
				row.profile_name = profile_label(row.provider, row.model)
		self._sync_active_profile()

	def _sync_active_profile(self):
		rows = list(self.get("profiles") or [])
		if not rows:
			return
		active = [row for row in rows if cint(row.is_active)]
		if len(active) > 1:
			keep = active[-1]
			for row in rows:
				row.is_active = 1 if row is keep else 0
			active = [keep]
		if not active:
			rows[0].is_active = 1
			active = [rows[0]]
		row = active[0]
		self.provider = row.provider or ""
		self.model = row.model or ""
		self.base_url = row.base_url or ""

	def on_update(self):
		if self.user:
			frappe.cache.hdel("bootinfo", self.user)
