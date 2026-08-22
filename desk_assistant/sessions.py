# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _

from desk_assistant.permissions import user_is_assistant_manager

HISTORY_CAP = 20
CONTENT_CAP = 8000
STORE_CAP = 20000
TOOL_PAYLOAD_CAP = 4000


def ensure_session(name: str | None) -> str:
	name = (name or "").strip()
	if name and frappe.db.exists("AI Chat Session", name):
		doc = frappe.get_doc("AI Chat Session", name)
		_assert_owner(doc)
		if doc.status == "Closed":
			doc.status = "Open"
			doc.save()
		return doc.name
	return _create()


def history_for_model(session: str) -> list[dict]:
	if not session or not frappe.db.exists("AI Chat Session", session):
		return []
	doc = frappe.get_doc("AI Chat Session", session)
	_assert_owner(doc)
	out = []
	for row in doc.messages or []:
		if row.role not in ("user", "assistant"):
			continue
		content = (row.content or "").strip()[:CONTENT_CAP]
		if content:
			out.append({"role": row.role, "content": content})
	return out[-HISTORY_CAP:]


def append_turn(
	session: str,
	user_text: str,
	assistant_text: str,
	provider: str = "",
	model: str = "",
	tool_rows: list[dict] | None = None,
) -> None:
	doc = frappe.get_doc("AI Chat Session", session)
	_assert_owner(doc)
	if not doc.title or doc.title == "Chat":
		snippet = (user_text or "").strip().split("\n")[0]
		doc.title = (snippet or "Chat")[:80]
	if provider:
		doc.provider = provider
	if model:
		doc.model = model
	doc.append("messages", {"role": "user", "content": (user_text or "")[:STORE_CAP]})
	for row in tool_rows or []:
		raw = row.get("tool_payload") or row.get("content") or ""
		payload = _as_json(raw)
		doc.append(
			"messages",
			{
				"role": "tool",
				"content": (row.get("content") or "")[:STORE_CAP],
				"tool_name": (row.get("tool_name") or row.get("name") or "")[:140],
				"tool_payload": payload,
			},
		)
	doc.append("messages", {"role": "assistant", "content": (assistant_text or "")[:STORE_CAP]})
	doc.save()


def public_session(session: str | None) -> dict:
	if not session or not frappe.db.exists("AI Chat Session", session):
		return {"session": None, "title": "", "messages": []}
	doc = frappe.get_doc("AI Chat Session", session)
	_assert_owner(doc)
	messages = [
		{"role": row.role, "content": row.content or ""}
		for row in (doc.messages or [])
		if row.role in ("user", "assistant") and (row.content or "").strip()
	]
	return {"session": doc.name, "title": doc.title or "", "messages": messages}


def latest_open_session() -> str | None:
	rows = frappe.get_all(
		"AI Chat Session",
		filters={"user": frappe.session.user, "status": "Open"},
		order_by="modified desc",
		limit=1,
		pluck="name",
	)
	return rows[0] if rows else None


def close_open_sessions() -> None:
	for name in frappe.get_all(
		"AI Chat Session",
		filters={"user": frappe.session.user, "status": "Open"},
		pluck="name",
	):
		frappe.db.set_value("AI Chat Session", name, "status", "Closed")


def _create() -> str:
	doc = frappe.get_doc(
		{
			"doctype": "AI Chat Session",
			"user": frappe.session.user,
			"status": "Open",
			"title": "Chat",
		}
	)
	doc.insert()
	return doc.name


def _assert_owner(doc) -> None:
	if user_is_assistant_manager():
		return
	if getattr(doc, "user", None) != frappe.session.user:
		frappe.throw(_("You can only access your own chat sessions."), frappe.PermissionError)


def _as_json(raw):
	if isinstance(raw, dict):
		return raw
	if isinstance(raw, str) and raw.strip():
		try:
			data = json.loads(raw)
		except json.JSONDecodeError:
			return {"raw": raw[:TOOL_PAYLOAD_CAP]}
		return data if isinstance(data, dict) else {"result": data}
	return {}
