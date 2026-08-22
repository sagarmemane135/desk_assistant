# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from frappe import _

from desk_assistant.providers.base import Completion, LLMConfig, ProviderError
from desk_assistant.providers.http import post_json
from desk_assistant.providers.toolfmt import anthropic_tools, parse_arguments

ANTHROPIC_VERSION = "2023-06-01"


def complete(
	config: LLMConfig,
	messages: list[dict],
	system: str | None = None,
	tools: list[dict] | None = None,
) -> Completion:
	url = f"{config.base_url}/v1/messages"
	payload = {
		"model": config.model,
		"max_tokens": config.max_tokens,
		"messages": _anthropic_messages(messages),
	}
	if system:
		payload["system"] = system
	formatted = anthropic_tools(tools)
	if formatted:
		payload["tools"] = formatted
	headers = {
		"x-api-key": config.api_key,
		"anthropic-version": ANTHROPIC_VERSION,
	}
	data = post_json(url, headers, payload)
	return _parse_completion(data)


def _anthropic_messages(messages: list[dict]) -> list[dict]:
	out = []
	pending = []

	def flush():
		if pending:
			out.append({"role": "user", "content": pending[:]})
			pending.clear()

	for item in messages:
		role = item.get("role")
		if role == "tool":
			pending.append(
				{
					"type": "tool_result",
					"tool_use_id": item.get("tool_call_id") or "",
					"content": item.get("content") or "",
				}
			)
			continue
		flush()
		if role == "assistant":
			content = []
			if item.get("content"):
				content.append({"type": "text", "text": item.get("content") or ""})
			for call in item.get("tool_calls") or []:
				content.append(
					{
						"type": "tool_use",
						"id": call.get("id") or "",
						"name": call.get("name") or "",
						"input": parse_arguments(call.get("arguments")),
					}
				)
			out.append({"role": "assistant", "content": content or (item.get("content") or "")})
		elif role == "user":
			out.append({"role": "user", "content": item.get("content") or ""})
	flush()
	if not out:
		raise ProviderError(_("Type a message."))
	return out


def _parse_completion(data: dict) -> Completion:
	if data.get("type") == "error":
		err = data.get("error") or {}
		msg = err.get("message") if isinstance(err, dict) else ""
		raise ProviderError(_("Provider error: {0}").format(str(msg or "error")[:240]))
	parts = []
	tool_calls = []
	for block in data.get("content") or []:
		if not isinstance(block, dict):
			continue
		if block.get("type") == "text":
			parts.append(block.get("text") or "")
		elif block.get("type") == "tool_use":
			name = block.get("name") or ""
			if not name:
				continue
			tool_calls.append(
				{
					"id": block.get("id") or f"toolu_{name}",
					"name": name,
					"arguments": parse_arguments(block.get("input")),
				}
			)
	text = "".join(parts).strip()
	if not text and not tool_calls:
		raise ProviderError(_("The provider returned an empty message."))
	usage = data.get("usage") or {}
	return Completion(
		text=text,
		token_in=int(usage.get("input_tokens") or 0),
		token_out=int(usage.get("output_tokens") or 0),
		tool_calls=tool_calls or None,
	)
