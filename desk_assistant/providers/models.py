# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import hashlib
import re

import frappe

from desk_assistant.providers.anthropic import ANTHROPIC_VERSION
from desk_assistant.providers.base import DEFAULT_BASE_URLS, ProviderError
from desk_assistant.providers.http import get_json

MODELS_CACHE_SECONDS = 300

MAX_MODELS = 250
OPENAI_SKIP = (
	"whisper",
	"tts",
	"davinci",
	"babbage",
	"ada-",
	"embedding",
	"dall-e",
	"moderation",
	"transcribe",
	"sora",
	"codex",
	"audio",
	"realtime",
	"image",
	"instruct",
	"search",
)

DATED_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")
PREFERRED = (
	"gpt-4o-mini",
	"gpt-4o",
	"gpt-4.1-mini",
	"gpt-4.1",
	"gpt-5-mini",
	"gpt-5-nano",
	"gpt-5",
	"claude-sonnet-4-5",
	"claude-haiku-4-5",
	"gemini-2.0-flash",
	"gemini-2.5-flash",
	"gemini-1.5-flash",
	"llama-3.3-70b-versatile",
	"llama-3.1-8b-instant",
	"openai/gpt-4o-mini",
	"openai/gpt-4o",
)


def list_models(provider: str, api_key: str, base_url: str | None = None) -> list[str]:
	provider = (provider or "").strip()
	base_url = (base_url or DEFAULT_BASE_URLS.get(provider) or "").rstrip("/")
	if not provider:
		raise ProviderError("Set a provider first.")
	cache_key = _models_cache_key(provider, base_url, api_key)
	if not getattr(frappe.flags, "in_test", False):
		cached = frappe.cache.get_value(cache_key)
		if isinstance(cached, list) and cached:
			return cached
	ids = _fetch_models(provider, api_key, base_url)
	if ids and not getattr(frappe.flags, "in_test", False):
		frappe.cache.set_value(cache_key, ids, expires_in_sec=MODELS_CACHE_SECONDS)
	return ids


def _fetch_models(provider: str, api_key: str, base_url: str) -> list[str]:
	if provider == "openai":
		return _openai_style(f"{base_url}/models", _bearer(api_key), _openai_chat_id)
	if provider == "anthropic":
		url = f"{base_url}/v1/models" if not base_url.endswith("/v1") else f"{base_url}/models"
		return _anthropic(url, api_key)
	if provider == "google":
		return _google(api_key, base_url)
	if provider == "openrouter":
		return _openai_style(
			f"{base_url}/models?output_modalities=text",
			_bearer(api_key),
			_openrouter_id,
		)
	if provider == "groq":
		return _openai_style(f"{base_url}/models", _bearer(api_key), _groq_id)
	if provider == "ollama":
		if not base_url:
			raise ProviderError("Set a Base URL first.")
		return _ollama_models(base_url, api_key)
	if provider == "openai_compatible":
		if not base_url:
			raise ProviderError("Set a Base URL first.")
		return _openai_style(f"{base_url}/models", _bearer(api_key), lambda i: i)
	raise ProviderError(f"Provider {provider} is not supported.")


def _models_cache_key(provider: str, base_url: str, api_key: str) -> str:
	digest = hashlib.sha256(f"{provider}|{base_url}|{api_key}".encode()).hexdigest()[:32]
	return f"desk_assistant:models:{digest}"


def _bearer(api_key: str) -> dict:
	return {"Authorization": f"Bearer {api_key}"}


def _openai_style(url: str, headers: dict, keep) -> list[str]:
	data = get_json(url, headers)
	ids = []
	for item in data.get("data") or []:
		if not isinstance(item, dict):
			continue
		mid = (item.get("id") or "").strip()
		if mid and keep(mid):
			ids.append(mid)
	return _prefer_chat_aliases(ids)


def _openai_chat_id(model_id: str) -> bool:
	low = model_id.lower()
	if any(skip in low for skip in OPENAI_SKIP):
		return False
	return low.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")) or "gpt" in low


def _openrouter_id(model_id: str) -> bool:
	low = model_id.lower()
	return not any(skip in low for skip in OPENAI_SKIP)


def _groq_id(model_id: str) -> bool:
	low = model_id.lower()
	return not any(skip in low for skip in ("whisper", "tts", "guard", "prompt-guard"))


def _ollama_models(base_url: str, api_key: str) -> list[str]:
	key = api_key or "ollama"
	try:
		ids = _openai_style(f"{base_url}/models", _bearer(key), lambda i: i)
		if ids:
			return ids
	except ProviderError:
		pass
	root = base_url.rstrip("/")
	if root.endswith("/v1"):
		root = root[:-3]
	data = get_json(f"{root}/api/tags")
	ids = []
	for item in data.get("models") or []:
		if not isinstance(item, dict):
			continue
		name = (item.get("name") or item.get("model") or "").strip()
		if name:
			ids.append(name)
	return _cap(ids)


def _anthropic(url: str, api_key: str) -> list[str]:
	data = get_json(
		url,
		{
			"x-api-key": api_key,
			"anthropic-version": ANTHROPIC_VERSION,
		},
	)
	ids = []
	for item in data.get("data") or []:
		if isinstance(item, dict) and item.get("id"):
			ids.append(item["id"].strip())
	return _prefer_chat_aliases(ids)


def _google(api_key: str, base_url: str | None = None) -> list[str]:
	from desk_assistant.providers.google import _root

	data = get_json(
		f"{_root(base_url)}/models?pageSize=200",
		{"x-goog-api-key": api_key},
	)
	ids = []
	for item in data.get("models") or []:
		if not isinstance(item, dict):
			continue
		methods = item.get("supportedGenerationMethods") or item.get("supported_generation_methods") or []
		if methods and "generateContent" not in methods:
			continue
		name = (item.get("name") or "").strip()
		if name.startswith("models/"):
			name = name[7:]
		low = name.lower()
		if any(skip in low for skip in ("embed", "imagen", "veo", "tts", "aqa")):
			continue
		if name:
			ids.append(name)
	return _prefer_chat_aliases(ids)


def _prefer_chat_aliases(ids: list[str]) -> list[str]:
	"""Keep chat models this key can see. Drop dated snapshots when an alias exists."""
	unique = _cap(ids)
	aliases = {mid for mid in unique if not DATED_SNAPSHOT.search(mid)}
	kept = []
	for mid in unique:
		if DATED_SNAPSHOT.search(mid) and DATED_SNAPSHOT.sub("", mid) in aliases:
			continue
		kept.append(mid)
	preferred = [mid for mid in PREFERRED if mid in kept]
	rest = [mid for mid in kept if mid not in preferred]
	return preferred + rest


def _cap(ids: list[str]) -> list[str]:
	seen = []
	for mid in ids:
		if mid not in seen:
			seen.append(mid)
	return seen[:MAX_MODELS]
