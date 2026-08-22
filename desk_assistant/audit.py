# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json

import frappe


def log_tool(
	session: str | None,
	name: str,
	arguments,
	result,
	duration_ms: int = 0,
	token_in: int = 0,
	token_out: int = 0,
) -> None:
	if not frappe.db.exists("DocType", "AI Assistant Audit Log"):
		return
	args = arguments if isinstance(arguments, dict) else {}
	target = str(args.get("doctype") or "").strip()
	if target and not frappe.db.exists("DocType", target):
		target = ""
	error = ""
	row_count = 0
	if isinstance(result, dict):
		if result.get("error"):
			error = str(result.get("error"))[:140]
		rows = result.get("rows")
		if isinstance(rows, list):
			row_count = len(rows)
	try:
		doc = frappe.get_doc(
			{
				"doctype": "AI Assistant Audit Log",
				"user": frappe.session.user,
				"session": session or None,
				"tool_name": (name or "")[:140],
				"target_doctype": target or None,
				"arguments": _safe_args(args),
				"row_count": row_count,
				"error": error,
				"duration_ms": int(duration_ms or 0),
				"token_in": int(token_in or 0),
				"token_out": int(token_out or 0),
			}
		)
		doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Desk Assistant audit log")


def _safe_args(args: dict) -> dict:
	clean = {key: value for key, value in args.items() if key not in ("api_key", "password")}
	raw = json.dumps(clean, default=str)
	if len(raw) <= 4000:
		return clean
	return {"_truncated": True, "keys": list(clean.keys())[:30]}
