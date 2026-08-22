# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from desk_assistant.providers.anthropic import complete as anthropic_complete
from desk_assistant.providers.base import COMPATIBLE_PROVIDERS, Completion, LLMConfig, ProviderError
from desk_assistant.providers.compatible import complete as compatible_complete
from desk_assistant.providers.google import complete as google_complete
from desk_assistant.providers.openai import complete as openai_complete
from desk_assistant.providers.resolve import public_llm_status, resolve_llm_config


def complete_chat(
	config: LLMConfig,
	messages: list[dict],
	system: str | None = None,
	tools: list[dict] | None = None,
	on_delta=None,
) -> Completion:
	kwargs = {"system": system, "tools": tools, "on_delta": on_delta}
	if config.provider == "openai":
		return openai_complete(config, messages, **kwargs)
	if config.provider == "anthropic":
		return anthropic_complete(config, messages, **kwargs)
	if config.provider == "google":
		return google_complete(config, messages, **kwargs)
	if config.provider in COMPATIBLE_PROVIDERS:
		return compatible_complete(config, messages, **kwargs)
	raise ProviderError(f"Provider {config.provider} is not supported.")


def complete_chat_iter(
	config: LLMConfig,
	messages: list[dict],
	system: str | None = None,
	tools: list[dict] | None = None,
):
	from desk_assistant.providers.anthropic import iter_complete as anthropic_iter
	from desk_assistant.providers.google import iter_complete as google_iter
	from desk_assistant.providers.openai import iter_complete as openai_iter

	if config.provider == "openai":
		yield from openai_iter(config, messages, system=system, tools=tools)
		return
	if config.provider == "anthropic":
		yield from anthropic_iter(config, messages, system=system, tools=tools)
		return
	if config.provider == "google":
		yield from google_iter(config, messages, system=system, tools=tools)
		return
	if config.provider in COMPATIBLE_PROVIDERS:
		extra = None
		if config.provider == "openrouter":
			extra = {
				"HTTP-Referer": "https://frappe.io",
				"X-Title": "Desk Assistant",
			}
		yield from openai_iter(
			config, messages, system=system, extra_headers=extra, tools=tools
		)
		return
	raise ProviderError(f"Provider {config.provider} is not supported.")


__all__ = [
	"Completion",
	"LLMConfig",
	"ProviderError",
	"complete_chat",
	"complete_chat_iter",
	"public_llm_status",
	"resolve_llm_config",
]
