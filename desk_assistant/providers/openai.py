# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from frappe import _

from desk_assistant.providers.base import Completion, LLMConfig, ProviderError
from desk_assistant.providers.http import iter_sse, post_json
from desk_assistant.providers.toolfmt import dump_arguments, openai_tools, parse_arguments


def complete(
	config: LLMConfig,
	messages: list[dict],
	system: str | None = None,
	extra_headers: dict | None = None,
	tools: list[dict] | None = None,
	on_delta=None,
) -> Completion:
	url, headers, payload = _prepare(config, messages, system, extra_headers, tools)
	if on_delta:
		result = None
		for item in iter_complete(
			config, messages, system=system, extra_headers=extra_headers, tools=tools
		):
			if isinstance(item, Completion):
				result = item
			else:
				on_delta(item)
		return result
	data = post_json(url, headers, payload)
	return _parse_completion(data)


def iter_complete(
	config: LLMConfig,
	messages: list[dict],
	system: str | None = None,
	extra_headers: dict | None = None,
	tools: list[dict] | None = None,
):
	url, headers, payload = _prepare(config, messages, system, extra_headers, tools)
	payload = dict(payload)
	payload["stream"] = True
	payload["stream_options"] = {"include_usage": True}
	yield from _iter_parsed_stream(iter_sse(url, headers, payload))


def _prepare(config, messages, system, extra_headers, tools):
	url = f"{config.base_url}/chat/completions"
	payload_messages = []
	if system:
		payload_messages.append({"role": "system", "content": system})
	payload_messages.extend(_openai_messages(messages))
	payload = {
		"model": config.model,
		"messages": payload_messages,
	}
	if _uses_max_completion_tokens(config):
		payload["max_completion_tokens"] = config.max_tokens
	else:
		payload["max_tokens"] = config.max_tokens
	formatted = openai_tools(tools)
	if formatted:
		payload["tools"] = formatted
		payload["tool_choice"] = "auto"
	headers = {
		"Authorization": f"Bearer {config.api_key}",
	}
	if extra_headers:
		headers.update(extra_headers)
	return url, headers, payload


def _iter_parsed_stream(events):
	parts = []
	tool_acc: dict[int, dict] = {}
	usage = {}
	for event in events:
		if event.get("usage"):
			usage = event["usage"]
		for choice in event.get("choices") or []:
			delta = choice.get("delta") or {}
			piece = _content_text(delta.get("content"), strip=False)
			if piece:
				parts.append(piece)
				yield piece
			for raw in delta.get("tool_calls") or []:
				if not isinstance(raw, dict):
					continue
				idx = int(raw.get("index") or 0)
				row = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
				row["id"] = raw.get("id") or row["id"]
				fn = raw.get("function") or {}
				row["name"] = fn.get("name") or row["name"]
				row["arguments"] = (row["arguments"] or "") + (fn.get("arguments") or "")
	text = "".join(parts).strip()
	tool_calls = []
	for idx in sorted(tool_acc):
		row = tool_acc[idx]
		if not row.get("name"):
			continue
		tool_calls.append(
			{
				"id": row.get("id") or f"call_{idx}_{row['name']}",
				"name": row["name"],
				"arguments": parse_arguments(row.get("arguments")),
			}
		)
	if not text and not tool_calls:
		raise ProviderError(_("The provider returned an empty message."))
	yield Completion(
		text=text,
		token_in=int(usage.get("prompt_tokens") or 0),
		token_out=int(usage.get("completion_tokens") or 0),
		tool_calls=tool_calls or None,
	)


def _openai_messages(messages: list[dict]) -> list[dict]:
	out = []
	for item in messages:
		role = item.get("role")
		if role == "tool":
			out.append(
				{
					"role": "tool",
					"tool_call_id": item.get("tool_call_id") or "",
					"content": item.get("content") or "",
				}
			)
			continue
		if role not in ("user", "assistant", "system"):
			continue
		msg = {"role": role, "content": item.get("content") or ""}
		if role == "assistant" and item.get("tool_calls"):
			msg["tool_calls"] = [
				{
					"id": call.get("id") or "",
					"type": "function",
					"function": {
						"name": call.get("name") or "",
						"arguments": dump_arguments(call.get("arguments")),
					},
				}
				for call in item["tool_calls"]
			]
			if not (msg["content"] or "").strip():
				msg["content"] = None
		out.append(msg)
	if not out:
		raise ProviderError(_("Type a message."))
	return out


def _parse_completion(data: dict) -> Completion:
	choices = data.get("choices") or []
	if not choices:
		err = data.get("error") or {}
		if isinstance(err, dict) and err.get("message"):
			raise ProviderError(_("Provider error: {0}").format(str(err["message"])[:240]))
		raise ProviderError(_("The provider returned no message."))
	message = choices[0].get("message") or {}
	tool_calls = _tool_calls(message.get("tool_calls"))
	text = _content_text(message.get("content"))
	if not text and not tool_calls:
		raise ProviderError(_("The provider returned an empty message."))
	usage = data.get("usage") or {}
	return Completion(
		text=text,
		token_in=int(usage.get("prompt_tokens") or 0),
		token_out=int(usage.get("completion_tokens") or 0),
		tool_calls=tool_calls,
	)


def _content_text(content, strip: bool = True) -> str:
	if isinstance(content, str):
		text = content
	elif isinstance(content, list):
		parts = []
		for block in content:
			if isinstance(block, dict) and block.get("type") == "text":
				parts.append(block.get("text") or "")
		text = "".join(parts)
	else:
		return ""
	return text.strip() if strip else text


def _tool_calls(raw) -> list[dict] | None:
	if not raw:
		return None
	out = []
	for i, item in enumerate(raw):
		if not isinstance(item, dict):
			continue
		fn = item.get("function") or {}
		name = fn.get("name") or item.get("name") or ""
		if not name:
			continue
		out.append(
			{
				"id": item.get("id") or f"call_{i}_{name}",
				"name": name,
				"arguments": parse_arguments(fn.get("arguments") or item.get("arguments")),
			}
		)
	return out or None


def _uses_max_completion_tokens(config: LLMConfig) -> bool:
	if config.provider == "ollama":
		return False
	leaf = (config.model or "").lower().split("/")[-1]
	return leaf.startswith(("o1", "o3", "o4", "gpt-5"))
