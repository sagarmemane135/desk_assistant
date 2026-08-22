# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json


def from_tool_rows(tool_rows: list | None) -> list[dict]:
	found: list[dict] = []
	seen: set[str] = set()
	for row in tool_rows or []:
		if not isinstance(row, dict):
			continue
		for payload in (row.get("tool_payload"), row.get("content"), row):
			for item in _from_payload(payload):
				name = item["name"]
				if name in seen:
					continue
				seen.add(name)
				found.append(item)
	return found


def from_session_messages(messages) -> list[dict]:
	found: list[dict] = []
	seen: set[str] = set()
	for row in messages or []:
		payload = getattr(row, "tool_payload", None) if not isinstance(row, dict) else row.get("tool_payload")
		role = getattr(row, "role", None) if not isinstance(row, dict) else row.get("role")
		if role != "tool" and not payload:
			continue
		for item in _from_payload(payload):
			name = item["name"]
			if name in seen:
				continue
			seen.add(name)
			found.append(item)
	return found


def _from_payload(raw) -> list[dict]:
	data = _as_dict(raw)
	if not data:
		return []
	out: list[dict] = []
	_add(out, data.get("name"), data.get("desk_path"))
	doc = data.get("doc")
	if isinstance(doc, dict):
		_add(out, doc.get("name") or data.get("name"), data.get("desk_path") or doc.get("desk_path"))
	for row in data.get("rows") or data.get("results") or []:
		if isinstance(row, dict):
			_add(out, row.get("name") or row.get("value"), row.get("desk_path"))
	return out


def _add(out: list[dict], name, path) -> None:
	name = str(name or "").strip()
	path = str(path or "").strip()
	if not name or not path.startswith("/desk/"):
		return
	if len(name) < 2:
		return
	out.append({"name": name, "desk_path": path})


def _as_dict(raw):
	if isinstance(raw, dict):
		return raw
	if isinstance(raw, str) and raw.strip():
		try:
			data = json.loads(raw)
		except json.JSONDecodeError:
			return {}
		return data if isinstance(data, dict) else {}
	return {}
