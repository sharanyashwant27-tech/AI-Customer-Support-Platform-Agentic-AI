"""Lightweight multi-language detection and translation (50+ languages)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.advanced.features import SUPPORTED_LANGUAGES, list_languages
from app.core.logging import get_logger
from app.llm.base import LLMMessage, StubLLMAdapter, get_llm_adapter

logger = get_logger(__name__)

SUPPORTED_LANGUAGE_CODES = {item["code"] for item in SUPPORTED_LANGUAGES}

# Heuristic script / keyword cues for offline detection
_LANG_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("hi", re.compile(r"[\u0900-\u097F]|(?:\b(namaste|dhanyavad|kripya)\b)", re.I)),
    ("es", re.compile(r"\b(hola|gracias|pedido|reembolso|ayuda|dónde|donde)\b", re.I)),
    ("fr", re.compile(r"\b(bonjour|merci|commande|remboursement|aide|où|ou)\b", re.I)),
    ("de", re.compile(r"\b(hallo|danke|bestellung|rückerstattung|hilfe|wo)\b", re.I)),
    ("pt", re.compile(r"\b(olá|ola|obrigado|pedido|reembolso|ajuda|onde)\b", re.I)),
    ("ar", re.compile(r"[\u0600-\u06FF]")),
    ("zh", re.compile(r"[\u4e00-\u9fff]")),
    ("ja", re.compile(r"[\u3040-\u30ff]")),
]

_PHRASE_BANK: dict[str, dict[str, str]] = {
    "es": {
        "connecting you with a human": "Te estoy conectando con un agente humano.",
        "i'm here to help": "Estoy aquí para ayudarte.",
    },
    "fr": {
        "connecting you with a human": "Je vous mets en relation avec un agent humain.",
        "i'm here to help": "Je suis là pour vous aider.",
    },
    "hi": {
        "connecting you with a human": "मैं आपको एक मानव एजेंट से जोड़ रहा हूँ।",
        "i'm here to help": "मैं आपकी मदद के लिए यहाँ हूँ।",
    },
    "de": {
        "connecting you with a human": "Ich verbinde Sie mit einem menschlichen Agenten.",
        "i'm here to help": "Ich bin hier, um zu helfen.",
    },
}


@dataclass
class LanguageResult:
    language: str
    confidence: float
    translated_text: str
    original_text: str


class LanguageService:
    """Detect language and translate to/from English for agent processing."""

    @staticmethod
    def supported_languages() -> dict:
        """Catalog of 50+ languages available for customer support."""
        return list_languages()

    def is_supported(self, language: str) -> bool:
        return language.lower() in SUPPORTED_LANGUAGE_CODES or language.lower().split("-")[0] in {
            c.split("-")[0] for c in SUPPORTED_LANGUAGE_CODES
        }

    def detect(self, text: str) -> tuple[str, float]:
        for code, pattern in _LANG_HINTS:
            if pattern.search(text):
                return code, 0.85
        # Default Latin script → English
        return "en", 0.6

    async def to_english(self, text: str, *, language: str | None = None) -> LanguageResult:
        detected, confidence = (language, 0.9) if language else self.detect(text)
        if detected == "en":
            return LanguageResult(
                language="en",
                confidence=confidence,
                translated_text=text,
                original_text=text,
            )

        llm = get_llm_adapter()
        if isinstance(llm, StubLLMAdapter):
            # Offline: keep original; agents still run on source text
            return LanguageResult(
                language=detected,
                confidence=confidence,
                translated_text=text,
                original_text=text,
            )

        response = await llm.complete(
            [
                LLMMessage(
                    role="system",
                    content=(
                        "Translate the user message into English. "
                        "Return only the translation, no commentary."
                    ),
                ),
                LLMMessage(role="user", content=text),
            ],
            temperature=0.0,
            max_tokens=1000,
        )
        return LanguageResult(
            language=detected,
            confidence=confidence,
            translated_text=response.content.strip() or text,
            original_text=text,
        )

    async def from_english(self, text: str, *, language: str) -> str:
        if not language or language == "en":
            return text

        lower = text.lower()
        bank = _PHRASE_BANK.get(language, {})
        for en, localized in bank.items():
            if en in lower:
                return localized

        llm = get_llm_adapter()
        if isinstance(llm, StubLLMAdapter):
            return f"[{language}] {text}"

        response = await llm.complete(
            [
                LLMMessage(
                    role="system",
                    content=(
                        f"Translate the assistant reply into language code '{language}'. "
                        "Return only the translation."
                    ),
                ),
                LLMMessage(role="user", content=text),
            ],
            temperature=0.0,
            max_tokens=1200,
        )
        return response.content.strip() or text


language_service = LanguageService()
