# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from desk_assistant.permissions import user_can_use_assistant, user_is_assistant_manager
from desk_assistant.providers.base import DEFAULT_BASE_URLS, DEFAULT_MODELS, ProviderError
from desk_assistant.providers.models import list_models as fetch_models
from desk_assistant.providers.resolve import _password


@frappe.whitelist()
def get_provider_defaults() -> dict:
	_assert_settings_access()
	return {"base_urls": dict(DEFAULT_BASE_URLS), "models": dict(DEFAULT_MODELS)}


@frappe.whitelist()
def list_models(
	provider: str | None = None,
	base_url: str | None = None,
	api_key: str | None = None,
	source: str | None = None,
	settings_doctype: str | None = None,
	settings_name: str | None = None,
	settings_user: str | None = None,
	profile_name: str | None = None,
) -> dict:
	_assert_settings_access()
	provider = (provider or "").strip()
	if not provider:
		return {"ok": False, "models": [], "message": _("Select a provider first.")}

	key = _usable_key(api_key)
	if not key:
		key = _saved_key(source, settings_doctype, settings_name, settings_user, profile_name)
	if provider == "ollama" and not key:
		key = "ollama"
	if not key:
		return {
			"ok": False,
			"models": [],
			"message": _(
				"This form's API key is hidden after Save. Fetch models uses the saved key for the User on this form. Paste again only if you have not saved yet."
			),
		}

	url = (base_url or "").strip() or DEFAULT_BASE_URLS.get(provider) or ""
	try:
		models = fetch_models(provider, key, url)
	except ProviderError as exc:
		return {"ok": False, "models": [], "message": str(exc)}

	return {
		"ok": True,
		"models": models,
		"base_url": url or DEFAULT_BASE_URLS.get(provider) or "",
		"default_model": DEFAULT_MODELS.get(provider) or "",
	}


def _assert_settings_access() -> None:
	if user_can_use_assistant() or user_is_assistant_manager():
		return
	frappe.throw(_("Desk Assistant is not enabled for this user."), frappe.PermissionError)


def _usable_key(api_key: str | None) -> str:
	key = (api_key or "").strip()
	if not key or set(key) <= {"*"}:
		return ""
	return key


def _saved_key(
	source: str | None,
	doctype: str | None = None,
	name: str | None = None,
	user: str | None = None,
	profile_name: str | None = None,
) -> str:
	"""Read the encrypted key for the row on the form, not the logged-in user."""
	source = (source or "user").strip()
	doctype = (doctype or "").strip()
	name = _lookup_name(name)
	user = (user or "").strip()
	profile_name = _lookup_name(profile_name)
	if profile_name:
		key = _password("User AI Model Profile", profile_name, "api_key")
		if key:
			return key
	if source == "site" or doctype == "AI Assistant Settings":
		return _password("AI Assistant Settings", "AI Assistant Settings", "default_api_key")
	for candidate in (name, user):
		if not candidate:
			continue
		key = _password("User AI Settings", candidate, "api_key")
		if key:
			return key
	if name or user:
		return ""
	return _password("User AI Settings", frappe.session.user, "api_key")


def _lookup_name(name: str | None) -> str:
	name = (name or "").strip()
	if not name or name in {"undefined", "null"} or name.startswith("new-"):
		return ""
	return name
