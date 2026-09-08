# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.modules.import_file import import_file_by_path
from frappe.tests.utils import FrappeTestCase

from desk_assistant.install import after_install, before_uninstall


def restore_nav_fixtures():
	app_path = frappe.get_app_path("desk_assistant")
	ordered = (
		("desk_assistant/workspace/desk_assistant/desk_assistant.json", "Workspace"),
		("workspace_sidebar/desk_assistant.json", "Workspace Sidebar"),
		("desktop_icon/desk_assistant.json", "Desktop Icon"),
	)
	for rel, doctype in ordered:
		if doctype != "Workspace" and not frappe.db.exists("DocType", doctype):
			continue
		path = os.path.join(app_path, rel)
		if os.path.exists(path):
			import_file_by_path(path, force=True)
	after_install()


class TestInstall(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		restore_nav_fixtures()
		super().tearDown()

	def test_before_uninstall_removes_desktop_icon(self):
		if not frappe.db.exists("DocType", "Desktop Icon") or not frappe.db.exists(
			"Desktop Icon", "Desk Assistant"
		):
			self.skipTest("v16 Desktop Icon fixture is not on this branch")
		before_uninstall()
		self.assertFalse(frappe.db.exists("Desktop Icon", "Desk Assistant"))
		self.assertFalse(frappe.get_all("Desktop Icon", filters={"app": "desk_assistant"}))
		if frappe.db.exists("DocType", "Workspace Sidebar"):
			self.assertFalse(frappe.db.exists("Workspace Sidebar", "Desk Assistant"))
