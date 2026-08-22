# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe

from desk_assistant.tools.guard import desk_path

SAFE_FIELDS = (
	"name",
	"full_name",
	"first_name",
	"last_name",
	"email",
	"user_type",
	"enabled",
	"language",
	"time_zone",
)


def run(_args: dict | None = None) -> dict:
	"""Signed-in user only. Does not list or load other User records."""
	user = frappe.session.user
	if not user or user == "Guest":
		return {"error": "permission_denied", "message": "Not signed in."}
	row = frappe.db.get_value("User", user, SAFE_FIELDS, as_dict=True) or {}
	roles = [r for r in frappe.get_roles(user) if r not in ("All", "Guest")]
	return {
		"user": user,
		"full_name": row.get("full_name") or user,
		"email": row.get("email") or user,
		"user_type": row.get("user_type"),
		"enabled": row.get("enabled"),
		"language": row.get("language"),
		"time_zone": row.get("time_zone"),
		"roles": roles,
		"desk_path": desk_path("User", user),
		"note": "Only the signed-in user. Other User records stay blocked.",
	}
