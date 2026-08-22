# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

"""Create limited Desk users for permission tests. Do not commit."""

import frappe

KEEP_ROLES = {"All", "Guest", "Desk User"}


def ensure_user(email: str, roles: list[str]) -> str:
	frappe.set_user("Administrator")
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0][:30],
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
		user.insert(ignore_permissions=True)
		user.reload()
	wanted = set(roles)
	keep = wanted | KEEP_ROLES
	user.roles = [row for row in user.roles if row.role in keep]
	have = {row.role for row in user.roles}
	for role in wanted - have:
		if frappe.db.exists("Role", role):
			user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return email
