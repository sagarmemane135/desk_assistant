# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from desk_assistant.boot import get_boot_payload
from desk_assistant.providers.base import Completion, LLMConfig, NO_KEY_MESSAGE, ProviderError
from desk_assistant.providers.openai import complete as openai_complete
from desk_assistant.providers.resolve import public_llm_status, resolve_llm_config

SITE = {"provider": "anthropic", "model": "claude-sonnet-4-5", "base_url": "", "max_tokens": 4096}
USER = {"provider": "openai", "model": "gpt-4o", "base_url": ""}


class TestProviders(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._prev_enabled = frappe.db.get_single_value("AI Assistant Settings", "enabled")
		frappe.db.set_single_value("AI Assistant Settings", "enabled", 1)

	def tearDown(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("DocType", "AI Assistant Settings"):
			frappe.db.set_single_value("AI Assistant Settings", "enabled", self._prev_enabled)
		super().tearDown()

	def test_boot_payload_never_includes_api_key_field(self):
		payload = get_boot_payload()
		self.assertNotIn("api_key", payload)
		self.assertNotIn("default_api_key", payload)
		self.assertIn("has_api_key", payload)
		self.assertIn("provider", payload)

	def test_get_status_never_includes_key(self):
		from desk_assistant.api.chat import get_status

		status = get_status()
		self.assertNotIn("api_key", status)
		self.assertIn("enabled", status)

	def test_user_key_wins_over_site(self):
		def password(doctype, name, field):
			if doctype == "User AI Settings":
				return "sk-user-secret-value"
			return "sk-site-secret-value"

		with (
			patch("desk_assistant.providers.resolve._user_row", return_value=USER),
			patch("desk_assistant.providers.resolve._active_profile", return_value=None),
			patch("desk_assistant.providers.resolve._site_defaults", return_value=SITE),
			patch("desk_assistant.providers.resolve._password", side_effect=password),
		):
			cfg = resolve_llm_config()
		self.assertEqual(cfg.source, "user")
		self.assertEqual(cfg.provider, "openai")
		self.assertEqual(cfg.api_key, "sk-user-secret-value")
		self.assertNotIn("sk-user-secret-value", repr(cfg))

	def test_site_key_fallback(self):
		def password(doctype, name, field):
			if doctype == "AI Assistant Settings":
				return "sk-site-secret-value"
			return ""

		with (
			patch("desk_assistant.providers.resolve._user_row", return_value=None),
			patch("desk_assistant.providers.resolve._active_profile", return_value=None),
			patch("desk_assistant.providers.resolve._site_defaults", return_value=SITE),
			patch("desk_assistant.providers.resolve._password", side_effect=password),
		):
			cfg = resolve_llm_config()
		self.assertEqual(cfg.source, "site")
		self.assertEqual(cfg.provider, "anthropic")
		self.assertEqual(cfg.api_key, "sk-site-secret-value")

	def test_missing_key_raises_spec_message(self):
		with (
			patch("desk_assistant.providers.resolve._user_row", return_value=USER),
			patch("desk_assistant.providers.resolve._active_profile", return_value=None),
			patch("desk_assistant.providers.resolve._site_defaults", return_value=SITE),
			patch("desk_assistant.providers.resolve._password", return_value=""),
		):
			with self.assertRaises(ProviderError) as ctx:
				resolve_llm_config(require_key=True)
		self.assertEqual(str(ctx.exception), str(NO_KEY_MESSAGE))

	def test_public_status_omits_key(self):
		with (
			patch("desk_assistant.providers.resolve._user_row", return_value=USER),
			patch("desk_assistant.providers.resolve._active_profile", return_value=None),
			patch("desk_assistant.providers.resolve._site_defaults", return_value=SITE),
			patch("desk_assistant.providers.resolve._password", return_value="sk-hidden"),
		):
			status = public_llm_status()
		self.assertTrue(status["has_api_key"])
		self.assertNotIn("api_key", status)
		self.assertNotIn("sk-hidden", frappe.as_json(status))

	def test_openai_complete_parses_message(self):
		cfg = LLMConfig(
			provider="openai",
			model="gpt-4o",
			api_key="sk-test",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)
		fake = {
			"choices": [{"message": {"content": "hello from model"}}],
			"usage": {"prompt_tokens": 3, "completion_tokens": 4},
		}
		with patch("desk_assistant.providers.openai.post_json", return_value=fake) as post:
			result = openai_complete(cfg, [{"role": "user", "content": "hi"}])
		self.assertEqual(result.text, "hello from model")
		self.assertEqual(result.token_out, 4)
		self.assertIsNone(result.tool_calls)
		self.assertIn("chat/completions", post.call_args[0][0])
		self.assertEqual(post.call_args[0][2]["max_tokens"], 256)
		self.assertNotIn("max_completion_tokens", post.call_args[0][2])

	def test_openai_parses_tool_calls(self):
		cfg = LLMConfig(
			provider="openai",
			model="gpt-4o",
			api_key="sk-test",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)
		fake = {
			"choices": [
				{
					"message": {
						"content": None,
						"tool_calls": [
							{
								"id": "call_abc",
								"type": "function",
								"function": {
									"name": "query",
									"arguments": '{"doctype":"ToDo","limit":1}',
								},
							}
						],
					}
				}
			],
			"usage": {},
		}
		with patch("desk_assistant.providers.openai.post_json", return_value=fake) as post:
			result = openai_complete(cfg, [{"role": "user", "content": "list todos"}], tools=[{"name": "query"}])
		self.assertEqual(result.text, "")
		self.assertEqual(result.tool_calls[0]["name"], "query")
		self.assertEqual(result.tool_calls[0]["arguments"]["doctype"], "ToDo")
		self.assertIn("tools", post.call_args[0][2])

	def test_gpt5_uses_max_completion_tokens(self):
		cfg = LLMConfig(
			provider="openai",
			model="gpt-5",
			api_key="sk-test",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)
		fake = {"choices": [{"message": {"content": "pong"}}], "usage": {}}
		with patch("desk_assistant.providers.openai.post_json", return_value=fake) as post:
			openai_complete(cfg, [{"role": "user", "content": "hi"}])
		payload = post.call_args[0][2]
		self.assertEqual(payload["max_completion_tokens"], 256)
		self.assertNotIn("max_tokens", payload)

	def test_send_returns_model_text_without_key(self):
		from desk_assistant.api.chat import send

		cfg = LLMConfig(
			provider="openai",
			model="gpt-4o",
			api_key="sk-must-not-leak",
			base_url="https://api.openai.com/v1",
			max_tokens=256,
			source="user",
		)
		with (
			patch("desk_assistant.api.chat.resolve_llm_config", return_value=cfg),
			patch(
				"desk_assistant.api.chat.run_agent",
				return_value={"text": "pong", "provider": "openai", "model": "gpt-4o"},
			),
		):
			out = send(message="ping")
		self.assertEqual(out["message"], "pong")
		self.assertEqual(out["provider"], "openai")
		self.assertNotIn("api_key", out)
		self.assertNotIn("sk-must-not-leak", frappe.as_json(out))

	def test_openai_list_filters_non_chat_models(self):
		from desk_assistant.providers.models import list_models

		fake = {
			"data": [
				{"id": "gpt-4o"},
				{"id": "gpt-4o-2024-08-06"},
				{"id": "whisper-1"},
				{"id": "text-embedding-3-small"},
				{"id": "gpt-3.5-turbo-instruct"},
				{"id": "gpt-4o-search-preview"},
			]
		}
		with patch("desk_assistant.providers.models.get_json", return_value=fake):
			ids = list_models("openai", "sk-x", "https://api.openai.com/v1")
		self.assertEqual(ids, ["gpt-4o"])

	def test_google_list_keeps_generate_content(self):
		from desk_assistant.providers.models import list_models

		fake = {
			"models": [
				{
					"name": "models/gemini-2.0-flash",
					"supportedGenerationMethods": ["generateContent"],
				},
				{
					"name": "models/embedding-001",
					"supportedGenerationMethods": ["embedContent"],
				},
			]
		}
		with patch("desk_assistant.providers.models.get_json", return_value=fake) as get:
			ids = list_models(
				"google",
				"key",
				"https://generativelanguage.googleapis.com/v1beta/openai",
			)
		self.assertEqual(ids, ["gemini-2.0-flash"])
		self.assertEqual(
			get.call_args[0][0],
			"https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
		)

	def test_google_complete_uses_generate_content(self):
		from desk_assistant.providers.google import complete as google_complete

		cfg = LLMConfig(
			provider="google",
			model="gemini-2.0-flash",
			api_key="gk-test",
			base_url="https://generativelanguage.googleapis.com/v1beta",
			max_tokens=256,
			source="user",
		)
		fake = {
			"candidates": [{"content": {"parts": [{"text": "hello gemini"}]}}],
			"usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3},
		}
		with patch("desk_assistant.providers.google.post_json", return_value=fake) as post:
			result = google_complete(cfg, [{"role": "user", "content": "hi"}])
		self.assertEqual(result.text, "hello gemini")
		self.assertIn("generateContent", post.call_args[0][0])
		self.assertEqual(post.call_args[0][1]["x-goog-api-key"], "gk-test")
		self.assertNotIn("gk-test", result.text)

	def test_google_parses_function_call(self):
		from desk_assistant.providers.google import complete as google_complete

		cfg = LLMConfig(
			provider="google",
			model="gemini-2.0-flash",
			api_key="gk-test",
			base_url="https://generativelanguage.googleapis.com/v1beta",
			max_tokens=256,
			source="user",
		)
		fake = {
			"candidates": [
				{
					"content": {
						"parts": [{"functionCall": {"name": "get_meta", "args": {"doctype": "ToDo"}}}]
					}
				}
			]
		}
		with patch("desk_assistant.providers.google.post_json", return_value=fake):
			result = google_complete(cfg, [{"role": "user", "content": "meta"}], tools=[{"name": "get_meta"}])
		self.assertEqual(result.tool_calls[0]["name"], "get_meta")
		self.assertEqual(result.tool_calls[0]["arguments"]["doctype"], "ToDo")

	def test_google_echoes_thought_signature(self):
		from desk_assistant.providers.google import complete as google_complete

		cfg = LLMConfig(
			provider="google",
			model="gemini-3.1-flash-lite",
			api_key="gk-test",
			base_url="https://generativelanguage.googleapis.com/v1beta",
			max_tokens=256,
			source="user",
		)
		first = {
			"candidates": [
				{
					"content": {
						"role": "model",
						"parts": [
							{
								"functionCall": {"name": "query", "args": {"doctype": "ToDo"}},
								"thoughtSignature": "sig-abc",
							}
						],
					}
				}
			]
		}
		with patch("desk_assistant.providers.google.post_json", return_value=first):
			result = google_complete(cfg, [{"role": "user", "content": "how many"}], tools=[{"name": "query"}])
		self.assertEqual(result.tool_calls[0]["thought_signature"], "sig-abc")
		self.assertEqual(result.vendor_content["parts"][0]["thoughtSignature"], "sig-abc")

		second = {"candidates": [{"content": {"parts": [{"text": "none"}]}}]}
		history = [
			{"role": "user", "content": "how many"},
			{
				"role": "assistant",
				"content": "",
				"tool_calls": result.tool_calls,
				"vendor_content": result.vendor_content,
			},
			{"role": "tool", "name": "query", "content": "{}"},
		]
		with patch("desk_assistant.providers.google.post_json", return_value=second) as post:
			google_complete(cfg, history, tools=[{"name": "query"}])
		contents = post.call_args[0][2]["contents"]
		model = next(row for row in contents if row["role"] == "model")
		self.assertEqual(model["parts"][0]["thoughtSignature"], "sig-abc")
		self.assertEqual(model["parts"][0]["functionCall"]["name"], "query")

	def test_google_tools_require_array_items(self):
		from desk_assistant.providers.toolfmt import google_tools
		from desk_assistant.tools.runner import SCHEMAS

		payload = google_tools(SCHEMAS)
		query = next(d for d in payload[0]["functionDeclarations"] if d["name"] == "query")
		props = query["parameters"]["properties"]
		for key in ("fields", "filters", "or_filters"):
			self.assertEqual(props[key]["type"], "array")
			self.assertIn("items", props[key])
		self.assertEqual(props["filters"]["items"]["type"], "array")
		self.assertIn("items", props["filters"]["items"])
		filled = google_tools(
			[
				{
					"name": "x",
					"description": "",
					"parameters": {
						"type": "object",
						"properties": {"filters": {"type": "array"}},
					},
				}
			]
		)
		self.assertEqual(
			filled[0]["functionDeclarations"][0]["parameters"]["properties"]["filters"]["items"],
			{"type": "string"},
		)

	def test_google_empty_explains_finish_reason(self):
		from desk_assistant.providers.google import complete as google_complete

		cfg = LLMConfig(
			provider="google",
			model="gemini-3.1-flash-lite",
			api_key="gk-test",
			base_url="https://generativelanguage.googleapis.com/v1beta",
			max_tokens=256,
			source="user",
		)
		fake = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}
		with patch("desk_assistant.providers.google.post_json", return_value=fake):
			with self.assertRaises(ProviderError) as ctx:
				google_complete(cfg, [{"role": "user", "content": "hi"}])
		self.assertIn("MAX_TOKENS", str(ctx.exception))

	def test_test_connection_uses_form_user(self):
		from desk_assistant.api.chat import test_connection

		cfg = LLMConfig(
			provider="google",
			model="gemini-2.0-flash",
			api_key="gk-test",
			base_url="https://generativelanguage.googleapis.com/v1beta",
			max_tokens=256,
			source="user",
		)
		with (
			patch("desk_assistant.api.chat.resolve_llm_config", return_value=cfg) as resolve,
			patch(
				"desk_assistant.api.chat.complete_chat",
				return_value=Completion(text="pong"),
			),
		):
			out = test_connection(settings_user="sagar.memane@example.com")
		self.assertEqual(out["provider"], "google")
		self.assertEqual(out["reply"], "pong")
		self.assertEqual(resolve.call_args.kwargs["user"], "sagar.memane@example.com")

	def test_anthropic_complete_parses_blocks(self):
		from desk_assistant.providers.anthropic import complete as anthropic_complete

		cfg = LLMConfig(
			provider="anthropic",
			model="claude-sonnet-4-5",
			api_key="sk-ant-test",
			base_url="https://api.anthropic.com",
			max_tokens=256,
			source="user",
		)
		fake = {
			"content": [{"type": "text", "text": "hello claude"}],
			"usage": {"input_tokens": 4, "output_tokens": 5},
		}
		with patch("desk_assistant.providers.anthropic.post_json", return_value=fake) as post:
			result = anthropic_complete(cfg, [{"role": "user", "content": "hi"}])
		self.assertEqual(result.text, "hello claude")
		self.assertIn("/v1/messages", post.call_args[0][0])
		self.assertEqual(post.call_args[0][1]["x-api-key"], "sk-ant-test")

	def test_anthropic_parses_tool_use(self):
		from desk_assistant.providers.anthropic import complete as anthropic_complete

		cfg = LLMConfig(
			provider="anthropic",
			model="claude-sonnet-4-5",
			api_key="sk-ant-test",
			base_url="https://api.anthropic.com",
			max_tokens=256,
			source="user",
		)
		fake = {
			"content": [
				{"type": "tool_use", "id": "toolu_1", "name": "search", "input": {"doctype": "ToDo", "txt": "x"}}
			],
			"usage": {},
		}
		with patch("desk_assistant.providers.anthropic.post_json", return_value=fake) as post:
			result = anthropic_complete(cfg, [{"role": "user", "content": "find x"}], tools=[{"name": "search"}])
		self.assertEqual(result.tool_calls[0]["id"], "toolu_1")
		self.assertEqual(result.tool_calls[0]["name"], "search")
		self.assertIn("tools", post.call_args[0][2])

	def test_ollama_falls_back_to_tags(self):
		from desk_assistant.providers.base import ProviderError
		from desk_assistant.providers.models import list_models

		tags = {"models": [{"name": "llama3.2:latest"}]}
		with patch(
			"desk_assistant.providers.models.get_json",
			side_effect=[ProviderError("down"), tags],
		):
			ids = list_models("ollama", "", "http://127.0.0.1:11434/v1")
		self.assertEqual(ids, ["llama3.2:latest"])

	def test_groq_is_a_chat_provider(self):
		from desk_assistant.providers.base import CHAT_PROVIDERS, DEFAULT_BASE_URLS

		self.assertIn("groq", CHAT_PROVIDERS)
		self.assertIn("groq", DEFAULT_BASE_URLS)

	def test_groq_list_skips_whisper(self):
		from desk_assistant.providers.models import list_models

		fake = {
			"data": [
				{"id": "llama-3.3-70b-versatile"},
				{"id": "whisper-large-v3"},
				{"id": "llama-guard-3-8b"},
			]
		}
		with patch("desk_assistant.providers.models.get_json", return_value=fake):
			ids = list_models("groq", "gsk-x", "https://api.groq.com/openai/v1")
		self.assertEqual(ids, ["llama-3.3-70b-versatile"])

	def test_complete_chat_routes_groq_to_openai_shape(self):
		from desk_assistant.providers import complete_chat

		cfg = LLMConfig(
			provider="groq",
			model="llama-3.3-70b-versatile",
			api_key="gsk-test",
			base_url="https://api.groq.com/openai/v1",
			max_tokens=256,
			source="user",
		)
		fake = {"choices": [{"message": {"content": "hello groq"}}], "usage": {}}
		with patch("desk_assistant.providers.openai.post_json", return_value=fake) as post:
			result = complete_chat(cfg, [{"role": "user", "content": "hi"}])
		self.assertEqual(result.text, "hello groq")
		self.assertIn("chat/completions", post.call_args[0][0])
		self.assertEqual(post.call_args[0][1]["Authorization"], "Bearer gsk-test")

	def test_list_models_api_omits_key(self):
		from desk_assistant.api.models import list_models as api_list

		with patch(
			"desk_assistant.api.models.fetch_models",
			return_value=["gpt-4o"],
		), patch("desk_assistant.api.models._saved_key", return_value="sk-hidden"):
			out = api_list(provider="openai")
		self.assertTrue(out["ok"])
		self.assertEqual(out["models"], ["gpt-4o"])
		self.assertNotIn("api_key", out)
		self.assertNotIn("sk-hidden", frappe.as_json(out))

	def test_list_models_uses_named_row_not_session_user(self):
		from desk_assistant.api.models import list_models as api_list

		def password(doctype, name, field):
			if name == "other@example.com":
				return "sk-other-user"
			return ""

		with patch(
			"desk_assistant.api.models.fetch_models",
			return_value=["gpt-4.1"],
		) as fetch, patch("desk_assistant.api.models._password", side_effect=password):
			out = api_list(
				provider="openai",
				source="user",
				settings_doctype="User AI Settings",
				settings_name="other@example.com",
				settings_user="other@example.com",
			)
		self.assertTrue(out["ok"])
		self.assertEqual(out["models"], ["gpt-4.1"])
		fetch.assert_called_once()
		self.assertEqual(fetch.call_args[0][1], "sk-other-user")

	def test_list_models_missing_named_row_does_not_use_session(self):
		from desk_assistant.api.models import list_models as api_list

		def password(doctype, name, field):
			if name == frappe.session.user:
				return "sk-session"
			return ""

		with patch("desk_assistant.api.models.fetch_models") as fetch, patch(
			"desk_assistant.api.models._password", side_effect=password
		):
			out = api_list(
				provider="openai",
				source="user",
				settings_name="missing@example.com",
			)
		self.assertFalse(out["ok"])
		fetch.assert_not_called()

	def test_retries_rate_limit_then_succeeds(self):
		import io
		import urllib.error
		from email.message import Message

		from desk_assistant.providers.http import get_json

		headers = Message()
		headers["Retry-After"] = "0"
		err = urllib.error.HTTPError(
			"https://api.example/v1", 429, "Too Many", headers, io.BytesIO(b"{}")
		)

		class Ok:
			def __enter__(self):
				return self

			def __exit__(self, *exc):
				return False

			def read(self):
				return b'{"ok": true}'

		with patch(
			"desk_assistant.providers.http.urllib.request.urlopen",
			side_effect=[err, Ok()],
		), patch("desk_assistant.providers.http.time.sleep") as slept:
			data = get_json("https://api.example/v1")
		self.assertEqual(data, {"ok": True})
		slept.assert_called()

	def test_rate_limit_message_suggests_lighter_model(self):
		from desk_assistant.providers.http import _public_http_error

		msg = _public_http_error(429, "")
		self.assertIn("rate limit", msg.lower())
		self.assertIn("gpt-4o-mini", msg)
