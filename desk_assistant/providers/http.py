# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import json
import time
import urllib.error
import urllib.request

from frappe import _

from desk_assistant.providers.base import ProviderHTTPError

MAX_RETRIES = 2
MAX_RETRY_WAIT = 8.0


def get_json(url: str, headers: dict | None = None, timeout: int = 30) -> dict:
	"""GET JSON. Never log headers (they may contain keys)."""
	req = urllib.request.Request(url, method="GET")
	for key, value in (headers or {}).items():
		req.add_header(key, value)
	return _read_json(req, timeout)


def post_json(url: str, headers: dict, payload: dict, timeout: int = 60) -> dict:
	"""POST JSON. Never log headers (they may contain keys)."""
	body = json.dumps(payload).encode("utf-8")
	req = urllib.request.Request(url, data=body, method="POST")
	req.add_header("Content-Type", "application/json")
	for key, value in headers.items():
		req.add_header(key, value)
	return _read_json(req, timeout)


def _read_json(req: urllib.request.Request, timeout: int, retries: int = MAX_RETRIES) -> dict:
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			raw = resp.read().decode("utf-8")
	except urllib.error.HTTPError as exc:
		if exc.code == 429 and retries > 0:
			wait = _retry_after_seconds(exc)
			_drain(exc)
			time.sleep(wait)
			return _read_json(req, timeout, retries - 1)
		err_body = _drain(exc)[:1500]
		raise ProviderHTTPError(exc.code, _public_http_error(exc.code, err_body)) from None
	except urllib.error.URLError:
		raise ProviderHTTPError(0, _("Could not reach the provider.")) from None
	except TimeoutError:
		raise ProviderHTTPError(0, _("The provider timed out.")) from None

	try:
		data = json.loads(raw)
	except json.JSONDecodeError:
		raise ProviderHTTPError(0, _("The provider returned an invalid response.")) from None
	if not isinstance(data, dict):
		raise ProviderHTTPError(0, _("The provider returned an invalid response."))
	return data


def _drain(exc: urllib.error.HTTPError) -> str:
	try:
		return exc.read().decode("utf-8", errors="replace")
	except Exception:
		return ""


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float:
	raw = ""
	if exc.headers:
		raw = exc.headers.get("Retry-After") or ""
	try:
		wait = float(raw)
	except (TypeError, ValueError):
		wait = 1.0
	return min(max(wait, 0.4), MAX_RETRY_WAIT)


def _public_http_error(status: int, body: str) -> str:
	if status == 401:
		return _("API key was rejected.")
	if status == 403:
		return _("The provider refused this request.")
	if status == 429:
		return _(
			"The provider hit a rate limit. Wait about a minute and try again, "
			"or switch to a lighter model such as gpt-4o-mini."
		)
	hint = _vendor_error_hint(body)
	if hint:
		return _("Provider error ({0}): {1}").format(status, hint)
	return _("Provider error ({0}).").format(status)


def _vendor_error_hint(body: str) -> str:
	try:
		data = json.loads(body)
	except json.JSONDecodeError:
		return ""
	err = data.get("error") if isinstance(data, dict) else None
	if isinstance(err, dict):
		msg = err.get("message") or err.get("type") or ""
	elif isinstance(err, str):
		msg = err
	else:
		msg = ""
	msg = str(msg).replace("\n", " ").strip()
	if any(token in msg.lower() for token in ("sk-", "api-key", "api_key", "bearer ")):
		return ""
	return msg[:240]
