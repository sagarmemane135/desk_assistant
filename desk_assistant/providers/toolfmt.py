# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import copy
import json


def openai_tools(schemas: list[dict] | None) -> list[dict] | None:
	if not schemas:
		return None
	return [
		{
			"type": "function",
			"function": {
				"name": item["name"],
				"description": item.get("description") or "",
				"parameters": item.get("parameters") or {"type": "object", "properties": {}},
			},
		}
		for item in schemas
	]


def anthropic_tools(schemas: list[dict] | None) -> list[dict] | None:
	if not schemas:
		return None
	return [
		{
			"name": item["name"],
			"description": item.get("description") or "",
			"input_schema": item.get("parameters") or {"type": "object", "properties": {}},
		}
		for item in schemas
	]


def google_tools(schemas: list[dict] | None) -> list[dict] | None:
	if not schemas:
		return None
	return [
		{
			"functionDeclarations": [
				{
					"name": item["name"],
					"description": item.get("description") or "",
					"parameters": _google_schema(
						copy.deepcopy(item.get("parameters") or {"type": "object", "properties": {}})
					),
				}
				for item in schemas
			]
		}
	]


def _google_schema(node):
	"""Gemini requires `items` on every ARRAY and rejects some OpenAPI extras."""
	if isinstance(node, list):
		return [_google_schema(item) for item in node]
	if not isinstance(node, dict):
		return node
	node.pop("additionalProperties", None)
	for key, value in list(node.items()):
		node[key] = _google_schema(value)
	if str(node.get("type") or "").lower() == "array" and "items" not in node:
		node["items"] = {"type": "string"}
	return node


def parse_arguments(raw) -> dict:
	if isinstance(raw, dict):
		return raw
	if isinstance(raw, str) and raw.strip():
		try:
			data = json.loads(raw)
		except json.JSONDecodeError:
			return {}
		return data if isinstance(data, dict) else {}
	return {}


def dump_arguments(raw) -> str:
	if isinstance(raw, str):
		return raw
	return json.dumps(raw or {}, default=str)
