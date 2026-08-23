# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from werkzeug.wrappers import Response

from desk_assistant.agent import iter_agent, run_agent
from desk_assistant.citations import from_tool_rows
from desk_assistant.language import language_lock, resolve_reply_language, with_user_lock
from desk_assistant.permissions import (
	assert_can_use_assistant,
	user_can_use_assistant,
	user_is_assistant_manager,
)
from desk_assistant.providers import complete_chat, public_llm_status, resolve_llm_config
from desk_assistant.providers.base import ProviderError
from desk_assistant.sessions import (
	append_turn,
	ensure_session,
	history_for_model,
	latest_open_session,
	close_open_sessions,
	public_session,
)

SYSTEM_PROMPT = """You are a Desk assistant. Use tools; do not invent documents or totals.
Reply in the language the user is writing in. If they ask to speak any language (Marathi, Hindi, Tamil, English, …), switch for the rest of this chat until they ask to change. Keep document names, desk_path links, field names, numbers, and ```chart JSON exactly as the tools returned them — do not translate those.
If a tool returns empty or permission_denied, say so honestly. Never guess invoice numbers, years, or amounts.
Default answer is short prose (who, amount, document link). Do not add a markdown table unless the user asks for a table, list, ranking, or breakdown, or several rows must be compared side by side. A single winner (“which customer has the largest overdue”) is a sentence plus the invoice link — no table. Do not add a chart unless the user asks for a chart, graph, plot, or visualization, or a short comparison (share, mix, or trend) would clearly help. Never invent table or chart numbers. Match the shape of the ask: chart-only → one-line caption and the fence, no table; table-only → table, no chart; both only if they asked for both. Chart values must be the same numbers the tools returned:
```chart
{"type":"bar","title":"Top 5","labels":["INV-1","INV-2"],"values":[10,20]}
```
type is bar, line, or pie. Keep labels short. Skip the fence if there are fewer than 2 numeric points.
Prefer query for lists, rankings, and year-wise invoice totals; run_report for named financial or stock reports the user can run; get_doc for one record; get_me for the signed-in user's name, email, or roles; search when the name is fuzzy; get_meta when you are unsure of field names.
Sales Analytics is a Sales Order report, not Sales Invoice. For sales invoices by year, query Sales Invoice with posting_date and docstatus=1. Do not run a report on a DocType the user cannot access.
The User DocType is blocked. Do not query or get_doc User, Has Role, or other users. For 'how many users' say you cannot list accounts. For 'my details' or 'my roles', call get_me.
When you mention a document name from tools, write only a markdown link: [My Learning Comapny](/app/company/My%20Learning%20Comapny). Never print the URL again in parentheses, and never leave a bare ID.
Calendar year vs fiscal year: if the user says a year such as 2023 without FY, use calendar 1 Jan–31 Dec and say that you used the calendar year.
The current screen is optional context, not a limit on what you can look up.
Submitted invoices use docstatus = 1. Rankings should set order_by and a small limit.
Fiscal Year has year, year_start_date, year_end_date, disabled — there is no is_default. Current fiscal year means disabled = 0 and today's date between year_start_date and year_end_date."""


@frappe.whitelist()
def get_status() -> dict:
	"""Safe probe for Desk JS. Never includes API keys."""
	if not user_can_use_assistant():
		return {"enabled": False, "provider": "", "model": "", "has_api_key": False}
	status = public_llm_status()
	status["enabled"] = True
	return status


@frappe.whitelist()
def send(message: str | None = None, session: str | None = None, context: str | None = None) -> dict:
	assert_can_use_assistant()
	text = (message or "").strip()
	if not text:
		frappe.throw(_("Type a message."))
	session_name = ensure_session(session)
	history = history_for_model(session_name)
	language = resolve_reply_language(text, history)
	reply = _complete(
		with_user_lock(text, language),
		context,
		history=history,
		session=session_name,
		language=language,
	)
	append_turn(
		session_name,
		text,
		reply["text"],
		provider=reply["provider"],
		model=reply["model"],
		tool_rows=reply.get("tool_rows"),
	)
	return {
		"ok": True,
		"error": None,
		"session": session_name,
		"provider": reply["provider"],
		"model": reply["model"],
		"message": reply["text"],
		"citations": from_tool_rows(reply.get("tool_rows")),
	}


@frappe.whitelist(methods=["POST"])
def stream(message: str | None = None, session: str | None = None, context: str | None = None):
	"""NDJSON token stream. Tool rounds emit status; the final answer emits delta lines."""
	assert_can_use_assistant()
	text = (message or "").strip()
	if not text:
		frappe.throw(_("Type a message."))
	session_name = ensure_session(session)
	history = history_for_model(session_name)
	language = resolve_reply_language(text, history)
	model_text = with_user_lock(text, language)

	def generate():
		yield _ndjson({"type": "session", "session": session_name})
		try:
			config = resolve_llm_config(require_key=True)
			for event in iter_agent(
				config,
				model_text,
				_system_prompt(context, language=language),
				use_tools=True,
				history=history,
				session=session_name,
				stream=True,
			):
				if event.get("type") == "done":
					reply = event["result"]
					append_turn(
						session_name,
						text,
						reply["text"],
						provider=reply["provider"],
						model=reply["model"],
						tool_rows=reply.get("tool_rows"),
					)
					if not frappe.flags.in_test:
						frappe.db.commit()
					yield _ndjson(
						{
							"type": "done",
							"session": session_name,
							"provider": reply["provider"],
							"model": reply["model"],
							"message": reply["text"],
							"citations": from_tool_rows(reply.get("tool_rows")),
						}
					)
				else:
					yield _ndjson(event)
		except ProviderError as exc:
			yield _ndjson({"type": "error", "message": str(exc)[:240]})
		except Exception as exc:
			frappe.log_error(title="Desk Assistant stream")
			hint = str(exc).strip().split("\n")[0][:160]
			yield _ndjson(
				{
					"type": "error",
					"message": _("Could not complete this reply.") + (f" {hint}" if hint else ""),
				}
			)

	response = Response(
		generate(),
		mimetype="application/x-ndjson",
		headers={
			"Cache-Control": "no-cache, no-store, no-transform",
			"X-Accel-Buffering": "no",
			"Content-Encoding": "identity",
		},
	)
	response.implicit_sequence_conversion = False
	response.automatically_set_content_length = False
	return response


def _ndjson(payload: dict) -> bytes:
	return (json.dumps(payload, default=str) + "\n").encode("utf-8")


@frappe.whitelist()
def get_open_session() -> dict:
	assert_can_use_assistant()
	return public_session(latest_open_session())


@frappe.whitelist()
def resume_session(session: str | None = None) -> dict:
	assert_can_use_assistant()
	name = (session or "").strip()
	if not name:
		frappe.throw(_("Pick a chat session."))
	return public_session(ensure_session(name))


@frappe.whitelist()
def new_session() -> dict:
	assert_can_use_assistant()
	close_open_sessions()
	return public_session(ensure_session(None))


@frappe.whitelist()
def test_connection(settings_user: str | None = None, profile: str | None = None) -> dict:
	assert_can_use_assistant()
	target = _settings_user(settings_user)
	reply = _complete(
		"Reply with the single word pong.",
		context=None,
		user=target,
		profile_name=profile,
		include_system=False,
	)
	return {
		"ok": True,
		"provider": reply["provider"],
		"model": reply["model"],
		"reply": (reply["text"] or "")[:200],
	}


def _complete(
	user_text: str,
	context: str | None,
	user: str | None = None,
	profile_name: str | None = None,
	include_system: bool = True,
	history: list | None = None,
	session: str | None = None,
	language: str | None = None,
) -> dict:
	try:
		config = resolve_llm_config(user=user, require_key=True, profile_name=profile_name)
		if include_system:
			result = run_agent(
				config,
				user_text,
				system=_system_prompt(context, language=language),
				use_tools=True,
				history=history,
				session=session,
			)
			text = result["text"]
			tool_rows = result.get("tool_rows") or []
		else:
			text = complete_chat(
				config,
				[{"role": "user", "content": user_text}],
				system=None,
			).text
			tool_rows = []
			result = {}
	except ProviderError as exc:
		frappe.throw(str(exc))
	return {
		"provider": config.provider,
		"model": config.model,
		"text": text,
		"tool_rows": tool_rows,
	}


def _settings_user(settings_user: str | None) -> str:
	target = (settings_user or "").strip() or frappe.session.user
	if target != frappe.session.user and not user_is_assistant_manager():
		frappe.throw(_("You can only test your own AI settings."), frappe.PermissionError)
	return target


def _system_prompt(context: str | None, language: str | None = None) -> str:
	prompt = SYSTEM_PROMPT
	lock = language_lock(language)
	if lock:
		prompt = lock + prompt + lock
	ctx = _parse_context(context)
	if ctx.get("doctype") and ctx.get("name"):
		prompt += (
			"\nThe user currently has {doctype} {name} open. "
			"That is optional context, not a restriction on the question."
		).format(doctype=ctx["doctype"], name=ctx["name"])
	return prompt


def _parse_context(context: str | None) -> dict:
	if not context:
		return {}
	if isinstance(context, dict):
		data = context
	else:
		try:
			data = json.loads(context)
		except (TypeError, json.JSONDecodeError):
			return {}
	if not isinstance(data, dict):
		return {}
	return {
		"doctype": (data.get("doctype") or "")[:140],
		"name": (data.get("name") or "")[:140],
		"route": (data.get("route") or "")[:240],
	}
