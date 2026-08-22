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
) -> Completion:
	if config.provider == "openai":
		return openai_complete(config, messages, system=system, tools=tools)
	if config.provider == "anthropic":
		return anthropic_complete(config, messages, system=system, tools=tools)
	if config.provider == "google":
		return google_complete(config, messages, system=system, tools=tools)
	if config.provider in COMPATIBLE_PROVIDERS:
		return compatible_complete(config, messages, system=system, tools=tools)
	raise ProviderError(f"Provider {config.provider} is not supported.")


__all__ = [
	"Completion",
	"LLMConfig",
	"ProviderError",
	"complete_chat",
	"public_llm_status",
	"resolve_llm_config",
]
