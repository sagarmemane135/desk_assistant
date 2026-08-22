# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from desk_assistant.permissions import user_can_use_assistant

DEFAULT_WIDTH = 360


def boot_session(bootinfo):
	"""Cache-miss path. extend_bootinfo re-applies on every Desk load (cached boot too)."""
	extend_bootinfo(bootinfo)


def extend_bootinfo(bootinfo):
	"""Always refresh the grant flag. boot_session only runs when bootinfo is rebuilt."""
	bootinfo.desk_assistant = get_boot_payload()


def get_boot_payload() -> dict:
	import frappe

	from desk_assistant.providers.resolve import public_llm_status

	payload = {
		"enabled": bool(user_can_use_assistant()),
		"sidebar_width": DEFAULT_WIDTH,
		"sidebar_collapsed": 0,
		"provider": "",
		"model": "",
		"has_api_key": False,
	}
	if not payload["enabled"]:
		return payload

	payload.update(public_llm_status())

	name = frappe.session.user
	if not frappe.db.exists("User AI Settings", name):
		return payload

	row = frappe.db.get_value(
		"User AI Settings",
		name,
		["sidebar_width", "sidebar_collapsed"],
		as_dict=True,
	)
	if row:
		payload["sidebar_width"] = int(row.sidebar_width or DEFAULT_WIDTH)
		payload["sidebar_collapsed"] = int(row.sidebar_collapsed or 0)
	return payload
