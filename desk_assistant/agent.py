# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json
import time

from desk_assistant.audit import log_tool
from desk_assistant.providers import complete_chat
from desk_assistant.providers.base import LLMConfig
from desk_assistant.tools.guard import max_tool_rounds
from desk_assistant.tools.runner import SCHEMAS, run_tool

LIMIT_MESSAGE = "I reached the lookup limit. Ask a narrower question, or try again."


def run_agent(
	config: LLMConfig,
	user_text: str,
	system: str | None,
	use_tools: bool = True,
	history: list | None = None,
	session: str | None = None,
) -> dict:
	messages = _clean_history(history)
	messages.append({"role": "user", "content": user_text})
	tools = SCHEMAS if use_tools else None
	rounds = max_tool_rounds() if use_tools else 0
	token_in = token_out = 0
	text = ""
	logged = []

	for step in range(rounds + 1):
		round_tools = tools if step < rounds else None
		result = complete_chat(config, messages, system=system, tools=round_tools)
		token_in += result.token_in
		token_out += result.token_out
		text = (result.text or "").strip()
		calls = [c for c in (result.tool_calls or []) if c.get("name")]
		if not calls or round_tools is None:
			break
		messages.append(
			{
				"role": "assistant",
				"content": result.text or "",
				"tool_calls": calls,
				"vendor_content": result.vendor_content,
			}
		)
		for call in calls:
			started = time.monotonic()
			payload = run_tool(call.get("name") or "", call.get("arguments"))
			duration_ms = int((time.monotonic() - started) * 1000)
			if session:
				log_tool(
					session,
					call.get("name") or "",
					call.get("arguments"),
					payload,
					duration_ms=duration_ms,
					token_in=result.token_in,
					token_out=result.token_out,
				)
			logged.append(
				{
					"tool_name": call.get("name") or "",
					"content": json.dumps(payload, default=str)[:4000],
					"tool_payload": json.dumps(payload, default=str)[:4000],
				}
			)
			messages.append(
				{
					"role": "tool",
					"tool_call_id": call.get("id") or "",
					"name": call.get("name") or "",
					"content": json.dumps(payload, default=str),
				}
			)

	if not text:
		text = LIMIT_MESSAGE if use_tools else ""
	return {
		"text": text,
		"provider": config.provider,
		"model": config.model,
		"token_in": token_in,
		"token_out": token_out,
		"tool_rows": logged,
	}


def _clean_history(history) -> list[dict]:
	out = []
	for item in history or []:
		if not isinstance(item, dict):
			continue
		role = item.get("role")
		if role not in ("user", "assistant"):
			continue
		content = str(item.get("content") or "").strip()[:8000]
		if content:
			out.append({"role": role, "content": content})
	return out[-20:]
