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
	frappe.clear_cache()


def after_migrate():
	ensure_roles()
	ensure_nav_roles()


def ensure_roles():
	for role in ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def ensure_nav_roles():
	"""Granted users see the Desk Assistant workspace, not only managers."""
	role = "AI Assistant User"
	for doctype, name in _nav_docs():
		if not frappe.db.exists(doctype, name):
			continue
		if frappe.db.exists("Has Role", {"parenttype": doctype, "parent": name, "role": role}):
			continue
		doc = frappe.get_doc(doctype, name)
		doc.append("roles", {"role": role})
		doc.save(ignore_permissions=True)


def _nav_docs():
	pairs = [("Workspace", "Desk Assistant")]
	if _has_roles_table("Desktop Icon") and frappe.db.exists("Desktop Icon", "Desk Assistant"):
		pairs.append(("Desktop Icon", "Desk Assistant"))
	return pairs


def _has_roles_table(doctype: str) -> bool:
	if not frappe.db.exists("DocType", doctype):
		return False
	return any(df.fieldname == "roles" and df.fieldtype == "Table" for df in frappe.get_meta(doctype).fields)
