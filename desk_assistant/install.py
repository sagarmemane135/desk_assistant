# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe

ROLES = (
	"AI Assistant Manager",
	"AI Assistant User",
)

APP_NAME = "desk_assistant"
APP_TITLE = "Desk Assistant"


def after_install():
	ensure_roles()
	ensure_nav_roles()
	restore_site_brand_logo()
	frappe.clear_cache()


def after_migrate():
	ensure_roles()
	ensure_nav_roles()
	restore_site_brand_logo()


def before_uninstall():
	remove_nav_artifacts()
	restore_site_brand_logo()
	frappe.clear_cache()


def after_uninstall():
	# Core after_app_uninstall still misses the icon (matches app_name, not title).
	remove_nav_artifacts()
	restore_site_brand_logo()
	frappe.clear_cache()


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
	for doctype, name in (("Workspace", APP_TITLE), ("Desktop Icon", APP_TITLE)):
		if not frappe.db.exists(doctype, name):
			continue
		if frappe.db.exists("Has Role", {"parenttype": doctype, "parent": name, "role": role}):
			continue
		doc = frappe.get_doc(doctype, name)
		doc.append("roles", {"role": role})
		doc.save(ignore_permissions=True)


def remove_nav_artifacts():
	"""Drop left-nav records Frappe core leaves behind after uninstall.

	`frappe.utils.install.delete_desktop_icon_and_sidebar` deletes Desktop Icons
	whose name equals the `app_name` hook (`desk_assistant`). Our icon is named
	`Desk Assistant` (the app title), so it stays in the system switcher.
	"""
	for doctype in ("Desktop Icon", "Workspace Sidebar", "Workspace"):
		if not frappe.db.exists("DocType", doctype):
			continue
		names = set()
		if frappe.db.exists(doctype, APP_TITLE):
			names.add(APP_TITLE)
		meta = frappe.get_meta(doctype)
		if meta.has_field("app"):
			names.update(frappe.get_all(doctype, filters={"app": APP_NAME}, pluck="name"))
		if meta.has_field("logo_url"):
			names.update(
				frappe.get_all(
					doctype,
					filters={"logo_url": ["like", f"%/{APP_NAME}/%"]},
					pluck="name",
				)
			)
		for name in names:
			frappe.delete_doc(
				doctype,
				name,
				force=True,
				ignore_permissions=True,
				ignore_on_trash=True,
				delete_permanently=True,
			)
	frappe.cache.delete_key("desktop_icons")
