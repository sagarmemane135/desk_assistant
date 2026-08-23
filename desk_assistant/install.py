# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe

ROLES = (
	"AI Assistant Manager",
	"AI Assistant User",
)


def after_install():
	ensure_roles()
	ensure_nav_roles()
	restore_site_brand_logo()
	frappe.clear_cache()


def after_migrate():
	ensure_roles()
	ensure_nav_roles()
	restore_site_brand_logo()


def ensure_roles():
	for role in ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def restore_site_brand_logo():
	"""Frappe uses the second `app_logo_url` hook as the navbar brand when exactly two apps set it.

	Desk Assistant is a sidebar, not the site product. Do not keep our SVG on Navbar / Website Settings.
	"""
	for doctype, field in (("Navbar Settings", "app_logo"), ("Website Settings", "app_logo")):
		if not frappe.db.exists("DocType", doctype):
			continue
		value = frappe.db.get_single_value(doctype, field)
		if value and "desk_assistant" in str(value):
			frappe.db.set_single_value(doctype, field, "")


def ensure_nav_roles():
	"""Granted users see the left Desk Assistant icon, not only managers."""
	role = "AI Assistant User"
	for doctype, name in (("Workspace", "Desk Assistant"), ("Desktop Icon", "Desk Assistant")):
		if not frappe.db.exists(doctype, name):
			continue
		if frappe.db.exists("Has Role", {"parenttype": doctype, "parent": name, "role": role}):
			continue
		doc = frappe.get_doc(doctype, name)
		doc.append("roles", {"role": role})
		doc.save(ignore_permissions=True)
