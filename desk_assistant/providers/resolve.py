# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.password import get_decrypted_password

from desk_assistant.providers.base import (
	CHAT_PROVIDERS,
	DEFAULT_BASE_URLS,
	DEFAULT_MODELS,
	LLMConfig,
	NO_KEY_MESSAGE,
	ProviderError,
)


def resolve_llm_config(
	user: str | None = None,
	require_key: bool = True,
	profile_name: str | None = None,
) -> LLMConfig:
	"""User key → site default. Never return this to the browser."""
	user = user or frappe.session.user
	site = _site_defaults()
	row = _user_row(user)
	profile = _profile_row(user, profile_name) if profile_name else _active_profile(user)
	if profile_name and not profile:
		raise ProviderError(_("Saved provider not found."))

	provider = (profile.get("provider") if profile else "") or (row.get("provider") if row else "") or site.get("provider") or ""
	model = (profile.get("model") if profile else "") or (row.get("model") if row else "") or site.get("model") or ""
	base_url = (profile.get("base_url") if profile else "") or (row.get("base_url") if row else "") or site.get("base_url") or ""
	user_key = _user_key(user, profile, row)
	site_key = _password("AI Assistant Settings", "AI Assistant Settings", "default_api_key")
	api_key = user_key or site_key
	source = "user" if user_key else ("site" if site_key else "")

	if provider == "ollama" and not api_key:
		api_key = "ollama"
		source = source or "ollama"

	if not provider:
		raise ProviderError(_("Set a provider on User AI Settings or AI Assistant Settings."))
	if provider not in CHAT_PROVIDERS:
		raise ProviderError(_("Provider {0} is not supported.").format(provider))

	if not model:
		model = DEFAULT_MODELS.get(provider) or ""
	if not model:
		raise ProviderError(_("Set a model on User AI Settings or AI Assistant Settings."))

	if not base_url:
		base_url = DEFAULT_BASE_URLS.get(provider) or ""
	if not base_url:
		raise ProviderError(_("Set a Base URL for this provider (required for OpenAI-compatible)."))
	base_url = base_url.rstrip("/")
	if provider == "anthropic" and base_url.endswith("/v1"):
		base_url = base_url[:-3].rstrip("/")

	if require_key and not api_key:
		raise ProviderError(NO_KEY_MESSAGE)

	max_tokens = max(256, min(32768, cint(site.get("max_tokens") or 4096)))
	return LLMConfig(
		provider=provider,
		model=model,
		api_key=api_key or "",
		base_url=base_url,
		max_tokens=max_tokens,
		source=source or "none",
	)


def public_llm_status(user: str | None = None) -> dict:
	"""Labels only. Never includes api_key."""
	try:
		cfg = resolve_llm_config(user=user, require_key=False)
	except ProviderError:
		return {"provider": "", "model": "", "has_api_key": False}
	return {
		"provider": cfg.provider,
		"model": cfg.model,
		"has_api_key": bool(cfg.api_key),
	}


def _site_defaults() -> dict:
	if not frappe.db.exists("DocType", "AI Assistant Settings"):
		return {}
	return {
		"provider": frappe.db.get_single_value("AI Assistant Settings", "default_provider") or "",
		"model": frappe.db.get_single_value("AI Assistant Settings", "default_model") or "",
		"base_url": frappe.db.get_single_value("AI Assistant Settings", "default_base_url") or "",
		"max_tokens": frappe.db.get_single_value("AI Assistant Settings", "max_tokens") or 4096,
	}


def _user_row(user: str) -> dict | None:
	if not frappe.db.exists("User AI Settings", user):
		return None
	row = frappe.db.get_value(
		"User AI Settings",
		user,
		["provider", "model", "base_url"],
		as_dict=True,
	)
	return row or None


def _active_profile(user: str) -> dict | None:
	if not frappe.db.exists("DocType", "User AI Model Profile"):
		return None
	if not frappe.db.exists("User AI Settings", user):
		return None
	row = frappe.db.get_value(
		"User AI Model Profile",
		{"parent": user, "parenttype": "User AI Settings", "is_active": 1},
		["name", "provider", "model", "base_url"],
		as_dict=True,
		order_by="idx desc",
	)
	return row or None


def _profile_row(user: str, name: str | None) -> dict | None:
	name = (name or "").strip()
	if not name:
		return None
	return frappe.db.get_value(
		"User AI Model Profile",
		{"name": name, "parent": user, "parenttype": "User AI Settings"},
		["name", "provider", "model", "base_url"],
		as_dict=True,
	)


def _user_key(user: str, profile: dict | None, row: dict | None) -> str:
	if profile and profile.get("name"):
		key = _password("User AI Model Profile", profile["name"], "api_key")
		if key:
			return key
		# One leftover parent key is OK for a single saved row; never reuse it
		# for a different provider after the user adds more profiles.
		count = frappe.db.count("User AI Model Profile", {"parent": user})
		if count > 1:
			return ""
	if row:
		return _password("User AI Settings", user, "api_key")
	return ""


def _password(doctype: str, name: str, field: str) -> str:
	try:
		value = get_decrypted_password(doctype, name, field, raise_exception=False)
	except Exception:
		return ""
	return (value or "").strip()
