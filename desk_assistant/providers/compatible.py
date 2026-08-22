# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from desk_assistant.providers.base import Completion, LLMConfig
from desk_assistant.providers.openai import complete as openai_complete


def complete(
	config: LLMConfig,
	messages: list[dict],
	system: str | None = None,
	tools: list[dict] | None = None,
	on_delta=None,
) -> Completion:
	"""OpenRouter, Ollama, Azure-compatible, Groq, vLLM — Chat Completions shape."""
	extra = None
	if config.provider == "openrouter":
		extra = {
			"HTTP-Referer": "https://frappe.io",
			"X-Title": "Desk Assistant",
		}
	return openai_complete(
		config, messages, system=system, extra_headers=extra, tools=tools, on_delta=on_delta
	)
