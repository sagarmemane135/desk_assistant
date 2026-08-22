# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from frappe.utils import cint

from desk_assistant.providers.resolve import _password


def profile_label(provider: str, model: str) -> str:
	return " · ".join([p for p in ((provider or "").strip(), (model or "").strip()) if p]) or "Profile"


def serialize_profiles(doc) -> list[dict]:
	out = []
	for row in doc.get("profiles") or []:
		name = row.name or ""
		has_key = bool(name and _password("User AI Model Profile", name, "api_key"))
		out.append(
			{
				"name": name,
				"label": (row.profile_name or "").strip() or profile_label(row.provider, row.model),
				"provider": row.provider or "",
				"model": row.model or "",
				"base_url": row.base_url or "",
				"has_api_key": has_key,
				"is_active": bool(cint(row.is_active)),
			}
		)
	return out


def ensure_legacy_profile(doc, save: bool = False) -> bool:
	"""Turn the old single provider/model/key into the first saved profile."""
	if doc.get("profiles") or not (doc.provider or doc.model):
		return False
	row = doc.append("profiles", {})
	row.provider = doc.provider or ""
	row.model = doc.model or ""
	row.base_url = doc.base_url or ""
	row.is_active = 1
	row.profile_name = profile_label(row.provider, row.model)
	key = _password("User AI Settings", doc.name, "api_key") if doc.name else ""
	if key:
		row.api_key = key
	if save and doc.name:
		doc.save()
	return True


def find_profile(doc, name: str | None):
	name = (name or "").strip()
	if not name or name.startswith("new-"):
		return None
	for row in doc.get("profiles") or []:
		if row.name == name:
			return row
	return None


def mark_active(doc, row) -> None:
	for item in doc.get("profiles") or []:
		item.is_active = 1 if item is row else 0
	doc.provider = row.provider or ""
	doc.model = row.model or ""
	doc.base_url = row.base_url or ""


def upsert_profile(doc, *, name: str | None, as_new: bool, provider: str, model: str, base_url: str, api_key: str):
	row = None if as_new else find_profile(doc, name)
	if row is None and not as_new:
		for item in doc.get("profiles") or []:
			if (item.provider or "") == provider and (item.model or "") == model:
				row = item
				break
	if row is None:
		row = doc.append("profiles", {})
	row.provider = provider
	row.model = model
	row.base_url = base_url
	if not (row.profile_name or "").strip():
		row.profile_name = profile_label(provider, model)
	if api_key:
		row.api_key = api_key
		doc.api_key = api_key
	mark_active(doc, row)
	return row
