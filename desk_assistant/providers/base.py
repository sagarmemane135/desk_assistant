# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from dataclasses import dataclass

from frappe import _


NO_KEY_MESSAGE = _("Ask admin to set a key or add your own in User AI Settings")

DEFAULT_BASE_URLS = {
	"openai": "https://api.openai.com/v1",
	"anthropic": "https://api.anthropic.com",
	"google": "https://generativelanguage.googleapis.com/v1beta",
	"groq": "https://api.groq.com/openai/v1",
	"openrouter": "https://openrouter.ai/api/v1",
	"ollama": "http://127.0.0.1:11434/v1",
}

DEFAULT_MODELS = {
	"openai": "gpt-4o",
	"anthropic": "claude-sonnet-4-5",
	"google": "gemini-2.0-flash",
	"groq": "llama-3.3-70b-versatile",
	"openrouter": "openai/gpt-4o-mini",
	"ollama": "llama3.2",
}

COMPATIBLE_PROVIDERS = frozenset({"openai_compatible", "openrouter", "ollama", "groq"})
CHAT_PROVIDERS = frozenset({"openai", "anthropic", "google"}) | COMPATIBLE_PROVIDERS


class ProviderError(Exception):
	"""User-facing provider failure. Message is safe to show in Desk."""


class ProviderHTTPError(ProviderError):
	def __init__(self, status: int, message: str):
		self.status = status
		super().__init__(message)


@dataclass
class LLMConfig:
	provider: str
	model: str
	api_key: str
	base_url: str
	max_tokens: int
	source: str

	def __repr__(self) -> str:
		return (
			f"LLMConfig(provider={self.provider!r}, model={self.model!r}, "
			f"has_key={bool(self.api_key)}, source={self.source!r})"
		)


@dataclass
class Completion:
	text: str
	token_in: int = 0
	token_out: int = 0
	tool_calls: list | None = None
	vendor_content: dict | None = None
