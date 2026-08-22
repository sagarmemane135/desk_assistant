# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json

from frappe import _

from desk_assistant.providers.base import DEFAULT_BASE_URLS, Completion, LLMConfig, ProviderError
from desk_assistant.providers.http import post_json
from desk_assistant.providers.toolfmt import google_tools, parse_arguments

NATIVE_ROOT = "https://generativelanguage.googleapis.com/v1beta"
SKIP_THOUGHT_SIGNATURE = "skip_thought_signature_validator"


def complete(
	config: LLMConfig,
	messages: list[dict],
	system: str | None = None,
	tools: list[dict] | None = None,
) -> Completion:
	model = (config.model or "").replace("models/", "").strip()
	if not model:
		raise ProviderError(_("Set a Gemini model."))
	url = f"{_root(config.base_url)}/models/{model}:generateContent"
	payload = {
		"contents": _contents(messages),
		"generationConfig": {"maxOutputTokens": config.max_tokens},
	}
	if system:
		payload["systemInstruction"] = {"parts": [{"text": system}]}
	formatted = google_tools(tools)
	if formatted:
		payload["tools"] = formatted
	data = post_json(url, {"x-goog-api-key": config.api_key}, payload)
	return _parse_completion(data)


def _root(base_url: str | None) -> str:
	url = (base_url or DEFAULT_BASE_URLS.get("google") or NATIVE_ROOT).rstrip("/")
	if url.endswith("/openai"):
		url = url[: -len("/openai")]
	if url.endswith("/v1beta"):
		return url
	return NATIVE_ROOT


def _contents(messages: list[dict]) -> list[dict]:
	out = []
	pending = []

	def flush():
		if pending:
			out.append({"role": "user", "parts": pending[:]})
			pending.clear()

	for item in messages:
		role = item.get("role")
		if role == "tool":
			pending.append({"functionResponse": _function_response(item)})
			continue
		flush()
		if role == "assistant":
			raw = item.get("vendor_content")
			if isinstance(raw, dict) and raw.get("parts"):
				out.append({"role": "model", "parts": raw["parts"]})
				continue
			parts = []
			if item.get("content"):
				parts.append({"text": item.get("content") or ""})
			for i, call in enumerate(item.get("tool_calls") or []):
				part = {
					"functionCall": {
						"name": call.get("name") or "",
						"args": parse_arguments(call.get("arguments")),
					}
				}
				sig = call.get("thought_signature")
				if sig:
					part["thoughtSignature"] = sig
				elif i == 0:
					part["thoughtSignature"] = SKIP_THOUGHT_SIGNATURE
				parts.append(part)
			out.append({"role": "model", "parts": parts or [{"text": ""}]})
		elif role == "user":
			out.append({"role": "user", "parts": [{"text": item.get("content") or ""}]})
	flush()
	if not out:
		raise ProviderError(_("Type a message."))
	return out


def _function_response(item: dict) -> dict:
	raw = item.get("content") or "{}"
	if isinstance(raw, dict):
		response = raw
	else:
		try:
			response = json.loads(raw)
		except (TypeError, json.JSONDecodeError):
			response = {"result": str(raw)}
	if not isinstance(response, dict):
		response = {"result": response}
	return {"name": item.get("name") or "tool", "response": response}


def _parse_completion(data: dict) -> Completion:
	err = data.get("error")
	if isinstance(err, dict) and err.get("message"):
		raise ProviderError(_("Provider error: {0}").format(str(err["message"])[:240]))
	feedback = data.get("promptFeedback") or {}
	blocked = feedback.get("blockReason")
	if blocked:
		raise ProviderError(_("Gemini blocked this prompt ({0}).").format(blocked))
	parts = []
	tool_calls = []
	finish = ""
	vendor_content = None
	for cand in data.get("candidates") or []:
		finish = cand.get("finishReason") or finish
		content = cand.get("content") or {}
		if vendor_content is None and content.get("parts"):
			vendor_content = content
		for part in content.get("parts") or []:
			if not isinstance(part, dict):
				continue
			if part.get("thought"):
				continue
			if part.get("text"):
				parts.append(part["text"])
			fc = part.get("functionCall") or part.get("function_call")
			if isinstance(fc, dict) and fc.get("name"):
				name = fc["name"]
				sig = (
					part.get("thoughtSignature")
					or part.get("thought_signature")
					or fc.get("thoughtSignature")
					or fc.get("thought_signature")
				)
				call = {
					"id": fc.get("id") or f"call_{len(tool_calls)}_{name}",
					"name": name,
					"arguments": parse_arguments(fc.get("args") or fc.get("arguments")),
				}
				if sig:
					call["thought_signature"] = sig
				tool_calls.append(call)
	text = "".join(parts).strip()
	if not text and not tool_calls:
		if finish and finish not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
			raise ProviderError(_("Gemini returned no text ({0}). Try another Gemini model.").format(finish))
		raise ProviderError(_("The provider returned an empty message."))
	usage = data.get("usageMetadata") or {}
	return Completion(
		text=text,
		token_in=int(usage.get("promptTokenCount") or 0),
		token_out=int(usage.get("candidatesTokenCount") or 0),
		tool_calls=tool_calls or None,
		vendor_content=vendor_content,
	)
