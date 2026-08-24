# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

import re

NAMES = {
	"marathi": "Marathi (मराठी)",
	"mr": "Marathi (मराठी)",
	"hindi": "Hindi (हिन्दी)",
	"hi": "Hindi (हिन्दी)",
	"english": "English",
	"en": "English",
	"tamil": "Tamil (தமிழ்)",
	"telugu": "Telugu (తెలుగు)",
	"kannada": "Kannada (ಕನ್ನಡ)",
	"gujarati": "Gujarati (ગુજરાતી)",
	"bengali": "Bengali (বাংলা)",
	"punjabi": "Punjabi (ਪੰਜਾਬੀ)",
	"urdu": "Urdu (اردو)",
	"arabic": "Arabic",
	"french": "French",
	"german": "German",
	"spanish": "Spanish",
	"portuguese": "Portuguese",
	"japanese": "Japanese",
	"korean": "Korean",
	"chinese": "Chinese",
	"russian": "Russian",
	"italian": "Italian",
}

SKIP = {
	"a",
	"an",
	"the",
	"this",
	"that",
	"it",
	"me",
	"my",
	"here",
	"there",
	"please",
	"now",
	"yes",
	"no",
	"to",
	"of",
	"for",
	"on",
	"at",
}

SPEAK_RE = re.compile(
	r"(?:speak|talk|reply|answer|respond|write|chat|switch)\s+"
	r"(?:to\s+me\s+)?(?:in\s+|to\s+)?([a-z]+)\b",
	re.I,
)
NATIVE = (
	("मराठी", "Marathi (मराठी)"),
	("हिंदी", "Hindi (हिन्दी)"),
	("हिन्दी", "Hindi (हिन्दी)"),
)


def detect_language(text: str | None) -> str | None:
	raw = (text or "").strip()
	if not raw:
		return None
	for needle, label in NATIVE:
		if needle in raw:
			return label
	match = SPEAK_RE.search(raw)
	if not match:
		return None
	key = match.group(1).lower()
	if key in SKIP:
		return None
	return NAMES.get(key) or key.title()


def resolve_reply_language(user_text: str | None, history: list | None = None) -> str | None:
	current = detect_language(user_text)
	if current:
		return None if current == "English" else current
	for row in reversed(history or []):
		if not isinstance(row, dict) or row.get("role") != "user":
			continue
		found = detect_language(row.get("content") or "")
		if found:
			return None if found == "English" else found
	return None


def language_lock(language: str | None) -> str:
	if not language:
		return ""
	return (
		f"\nCRITICAL LANGUAGE LOCK: The user asked to speak {language}. "
		f"Write every sentence of this reply in {language}. "
		"Do not use English except document names, /desk/ links, numbers, and ```chart JSON.\n"
	)


def with_user_lock(user_text: str, language: str | None) -> str:
	text = (user_text or "").strip()
	if not language:
		return text
	return f"{text}\n\n(Reply in {language} only. Do not answer in English.)"
