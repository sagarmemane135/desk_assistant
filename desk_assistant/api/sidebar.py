# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint

from desk_assistant.permissions import assert_can_use_assistant
from desk_assistant.utils.profiles import (
	ensure_legacy_profile,
	find_profile,
	mark_active,
	serialize_profiles,
	upsert_profile,
)
from desk_assistant.providers.base import DEFAULT_BASE_URLS, DEFAULT_MODELS
from desk_assistant.providers.resolve import _password, public_llm_status

MIN_WIDTH = 320
MAX_WIDTH = 900
DEFAULT_WIDTH = 360


def get_or_create_user_settings():
	user = frappe.session.user
	if frappe.db.exists("User AI Settings", user):
		return frappe.get_doc("User AI Settings", user)
	doc = frappe.new_doc("User AI Settings")
	doc.user = user
	doc.sidebar_width = DEFAULT_WIDTH
	doc.insert()
	return doc


def _settings_with_profiles():
	doc = get_or_create_user_settings()
	if ensure_legacy_profile(doc, save=True):
		doc.reload()
	return doc


@frappe.whitelist()
def save_prefs(width: int | str | None = None, collapsed: int | str | None = None) -> dict:
	"""Persist sidebar layout without bumping modified (form timestamp stays valid)."""
	assert_can_use_assistant()
	doc = get_or_create_user_settings()
	values = {}
	if width is not None:
		next_width = max(MIN_WIDTH, min(MAX_WIDTH, cint(width)))
		if cint(doc.sidebar_width) != next_width:
			values["sidebar_width"] = next_width
	if collapsed is not None:
		next_collapsed = 1 if cint(collapsed) else 0
		if cint(doc.sidebar_collapsed or 0) != next_collapsed:
			values["sidebar_collapsed"] = next_collapsed
	if values:
		frappe.db.set_value("User AI Settings", doc.name, values, update_modified=False)
	return {
		"sidebar_width": values.get("sidebar_width", cint(doc.sidebar_width) or DEFAULT_WIDTH),
		"sidebar_collapsed": values.get("sidebar_collapsed", cint(doc.sidebar_collapsed or 0)),
	}


@frappe.whitelist()
def get_llm_settings() -> dict:
	"""Labels only. Never includes api_key."""
	assert_can_use_assistant()
	doc = _settings_with_profiles()
	profiles = serialize_profiles(doc)
	active = next((row for row in profiles if row["is_active"]), None)
	has_key = bool(active and active["has_api_key"]) or bool(
		_password("User AI Settings", doc.name, "api_key")
	)
	status = public_llm_status()
	return {
		"provider": (active or {}).get("provider") or doc.provider or "",
		"model": (active or {}).get("model") or doc.model or "",
		"base_url": (active or {}).get("base_url") or doc.base_url or "",
		"has_api_key": has_key,
		"active_provider": status.get("provider") or "",
		"active_model": status.get("model") or "",
		"profile": (active or {}).get("name") or "",
		"profiles": profiles,
		"base_urls": dict(DEFAULT_BASE_URLS),
		"models": dict(DEFAULT_MODELS),
	}


@frappe.whitelist()
def save_llm_settings(
	provider: str | None = None,
	model: str | None = None,
	llm_model: str | None = None,
	base_url: str | None = None,
	api_key: str | None = None,
	profile: str | None = None,
	as_new: int | str | None = None,
) -> dict:
	assert_can_use_assistant()
	doc = _settings_with_profiles()
	provider = (provider or "").strip()
	model = (llm_model or model or "").strip()
	base_url = (base_url or "").strip()
	key = (api_key or "").strip()
	if key and not (set(key) - {"*"}):
		key = ""
	upsert_profile(
		doc,
		name=profile,
		as_new=bool(cint(as_new)),
		provider=provider,
		model=model,
		base_url=base_url,
		api_key=key,
	)
	doc.save()
	out = get_llm_settings()
	out["ok"] = True
	return out


@frappe.whitelist()
def activate_profile(profile: str | None = None) -> dict:
	assert_can_use_assistant()
	doc = _settings_with_profiles()
	row = find_profile(doc, profile)
	if not row:
		frappe.throw(_("Select a saved provider first."))
	mark_active(doc, row)
	doc.save()
	out = get_llm_settings()
	out["ok"] = True
	return out


@frappe.whitelist()
def delete_profile(profile: str | None = None) -> dict:
	assert_can_use_assistant()
	doc = _settings_with_profiles()
	row = find_profile(doc, profile)
	if not row:
		frappe.throw(_("Select a saved provider first."))
	was_active = cint(row.is_active)
	doc.remove(row)
	if was_active and doc.get("profiles"):
		mark_active(doc, doc.profiles[0])
	elif not doc.get("profiles"):
		doc.provider = ""
		doc.model = ""
		doc.base_url = ""
	doc.save()
	out = get_llm_settings()
	out["ok"] = True
	return out
