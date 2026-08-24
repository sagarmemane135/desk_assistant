# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json

import frappe

from desk_assistant.permissions import user_can_use_assistant
from desk_assistant.tools import get_doc, get_me, get_meta, query, report, search

MAX_RESULT_CHARS = 12000

SCHEMAS = [
	{
		"name": "get_meta",
		"description": "Field names, types, and Link targets for a DocType. Call before query if unsure of columns.",
		"parameters": {
			"type": "object",
			"properties": {"doctype": {"type": "string"}},
			"required": ["doctype"],
		},
	},
	{
		"name": "search",
		"description": "Find documents by a short text, then use query or get_doc with the exact name.",
		"parameters": {
			"type": "object",
			"properties": {
				"doctype": {"type": "string"},
				"txt": {"type": "string"},
				"limit": {"type": "integer"},
			},
			"required": ["doctype", "txt"],
		},
	},
	{
		"name": "query",
		"description": (
			"List or rank documents with Desk filters (same engine as list views). "
			"Use posting_date between for a calendar year, e.g. [\"2023-01-01\", \"2023-12-31\"]. "
			"Submitted invoices use docstatus=1. Link columns look like customer.customer_name. "
			"Aggregates (sum/count) need group_by. Always set order_by and a small limit for rankings. "
			"Who holds a role: query Has Role with role, or query User then get_doc for roles, if permitted."
		),
		"parameters": {
			"type": "object",
			"properties": {
				"doctype": {"type": "string"},
				"fields": {"type": "array", "items": {"type": "string"}},
				"filters": {
					"type": "array",
					"description": (
						'Frappe filters, e.g. [["posting_date", "between", ["2023-01-01", "2023-12-31"]], '
						'["docstatus", "=", "1"]]'
					),
					"items": {
						"type": "array",
						"description": "One filter: [field, operator, value]. For between, value is [from, to].",
						"items": {"type": "string"},
					},
				},
				"or_filters": {
					"type": "array",
					"description": "Same shape as filters; any one may match.",
					"items": {
						"type": "array",
						"description": "One filter: [field, operator, value].",
						"items": {"type": "string"},
					},
				},
				"group_by": {"type": "string"},
				"order_by": {"type": "string"},
				"limit": {"type": "integer"},
			},
			"required": ["doctype"],
		},
	},
	{
		"name": "get_doc",
		"description": "Load one document the user can read. Password fields are stripped.",
		"parameters": {
			"type": "object",
			"properties": {
				"doctype": {"type": "string"},
				"name": {"type": "string"},
			},
			"required": ["doctype", "name"],
		},
	},
	{
		"name": "get_me",
		"description": (
			"The signed-in Desk user: name, email, type, and roles. "
			"Use for 'who am I', 'my details', or 'my roles'. "
			"To list other users or who holds a role, query User or Has Role when this session can read them."
		),
		"parameters": {"type": "object", "properties": {}},
	},
	{
		"name": "run_report",
		"description": (
			"Run a Query Report the user is allowed to run (P&L, Trial Balance, General Ledger, stock). "
			"Cannot draw charts. Account DocType has no live balances — use Trial Balance or P&L. "
			"Profit and Loss / Balance Sheet filters: company, filter_based_on "
			"('Fiscal Year' or 'Date Range'), from_fiscal_year and to_fiscal_year "
			"(Fiscal Year names like 2026-2027) or period_start_date and period_end_date, periodicity Yearly. "
			"Trial Balance: company, fiscal_year, from_date, to_date. "
			"General Ledger: company, from_date, to_date. "
			"Sales Analytics reports on Sales Order, not invoices. "
			"If the report fails, read filters_used and hint, fix keys, and retry."
		),
		"parameters": {
			"type": "object",
			"properties": {
				"report": {"type": "string"},
				"filters": {"type": "object"},
			},
			"required": ["report"],
		},
	},
]

HANDLERS = {
	"get_meta": get_meta.run,
	"search": search.run,
	"query": query.run,
	"get_doc": get_doc.run,
	"get_me": get_me.run,
	"run_report": report.run,
}


def run_tool(name: str, arguments) -> dict:
	if not user_can_use_assistant():
		return {"error": "not_enabled"}
	handler = HANDLERS.get(name)
	if not handler:
		return {"error": "unknown_tool", "name": name}
	args = _parse_args(arguments)
	try:
		result = handler(args)
	except Exception as exc:
		frappe.clear_messages()
		return {"error": "tool_failed", "name": name, "message": str(exc)[:240]}
	# Caught PermissionError still queues a Desk modal via _server_messages.
	frappe.clear_messages()
	return _cap(result if isinstance(result, dict) else {"result": result})


def _parse_args(arguments) -> dict:
	if isinstance(arguments, dict):
		return arguments
	if isinstance(arguments, str) and arguments.strip():
		try:
			data = json.loads(arguments)
		except json.JSONDecodeError:
			return {}
		return data if isinstance(data, dict) else {}
	return {}


def _cap(payload: dict) -> dict:
	raw = json.dumps(payload, default=str)
	if len(raw) <= MAX_RESULT_CHARS:
		return payload
	if isinstance(payload.get("rows"), list):
		payload = dict(payload)
		payload["rows"] = payload["rows"][:10]
		payload["truncated"] = True
		payload["note"] = "Result truncated."
		raw = json.dumps(payload, default=str)
		if len(raw) <= MAX_RESULT_CHARS:
			return payload
	return {"error": "too_large", "message": "Tool result was too large."}
