"""Redact contact-center PII before a cloud LLM call.

Matches are replaced with ``[PII_DATA]``. ``anonymize_with_vault`` keeps the
originals in memory so the same request can restore tokens. The vault is never
logged. ``prepare_text_for_llm`` returns only the redacted text.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.core.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

REPLACEMENT = "[PII_DATA]"

_DIGIT_WORD = (
    r"(?:ноль|один|одна|два|две|три|четыре|пять|шесть|семь|восемь|девять|"
    r"nol|bir|ikki|uch|to['’ʻ`]?rt|tort|besh|olti|yetti|sakkiz|to['’ʻ`]?qqiz|toqqiz)"
)
_NAME_CUE = (
    r"меня\s+зовут|моё\s+имя|мое\s+имя|менинг\s+исмим|mening\s+ismim|исмим|ismim"
)
_NAME_VALUE = (
    r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'’-]{1,40}"
    r"(?:\s+[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'’-]{1,40})?"
)

# Longer identifiers first so a PINFL or card is not partially matched as a phone.
_PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    (
        "EMAIL_ADDRESS",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        0,
    ),
    (
        "CREDIT_CARD",
        re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        0,
    ),
    ("UZBEK_PINFL", re.compile(r"\b\d{14}\b"), 0),
    ("PASSPORT", re.compile(r"\b[A-Z]{2}\d{7}\b"), 0),
    (
        "PHONE_NUMBER",
        re.compile(
            r"\+998[\s-]?(?:90|91|93|94|95|97|98|99|33|88)[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"
        ),
        0,
    ),
    (
        "PHONE_NUMBER",
        re.compile(
            r"\b998[\s-]?(?:90|91|93|94|95|97|98|99|33|88)[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"
        ),
        0,
    ),
    (
        "PHONE_NUMBER",
        re.compile(r"\b(?:90|91|93|94|95|97|98|99|33|88)[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b"),
        0,
    ),
    (
        "SPOKEN_NUMBER",
        re.compile(rf"(?i)(?<!\w){_DIGIT_WORD}(?:[\s,.\-]+{_DIGIT_WORD}){{6,}}(?!\w)"),
        0,
    ),
    (
        "PERSON",
        re.compile(rf"(?i:\b(?:{_NAME_CUE})\s+)({_NAME_VALUE})"),
        1,
    ),
    (
        "ADDRESS",
        re.compile(
            r"(?i)\b(?:улиц[аеуы]|ул\.|проспект|пр-т|махалл[аяи]|mahalla|"
            r"ko['’ʻ`]?cha|kocha)\s+[0-9A-Za-zА-Яа-яЁё'’-]{1,40}(?:\s+\d{1,4}[a-zа-я]?)?"
        ),
        0,
    ),
    (
        "ADDRESS",
        re.compile(r"(?i)(?<!\w)(?:дом|квартира|кв\.|honadon|uy)\s*№?\s*\d{1,4}[a-zа-я]?(?!\w)"),
        0,
    ),
]


@dataclass
class PiiVault:
    """In-memory originals in replacement order. Encrypt before persisting."""

    values: list[str]

    def restore(self, text: str) -> str:
        index = 0

        def repl(match: re.Match[str]) -> str:
            nonlocal index
            if index >= len(self.values):
                return match.group(0)
            value = self.values[index]
            index += 1
            return value

        return re.sub(re.escape(REPLACEMENT), repl, text)

    def encrypted(self) -> str:
        return encrypt_value(json.dumps(self.values, ensure_ascii=False))

    @classmethod
    def from_encrypted(cls, blob: str) -> PiiVault:
        raw = json.loads(decrypt_value(blob))
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise ValueError("Некорректное хранилище PII")
        return cls(values=raw)


def _apply(pattern: re.Pattern[str], text: str, values: list[str], group: int) -> str:
    def repl(match: re.Match[str]) -> str:
        values.append(match.group(group))
        if group == 0:
            return REPLACEMENT
        full = match.group(0)
        start, end = match.span(group)
        base = match.start()
        return full[: start - base] + REPLACEMENT + full[end - base :]

    return pattern.sub(repl, text)


def anonymize_with_vault(text: str) -> tuple[str, PiiVault]:
    if not text:
        return text, PiiVault(values=[])
    values: list[str] = []
    result = text
    for entity, pattern, group in _PATTERNS:
        before = len(values)
        result = _apply(pattern, result, values, group)
        found = len(values) - before
        if found and logger.isEnabledFor(logging.DEBUG):
            logger.debug("PII %s matched %d time(s)", entity, found)
    return result, PiiVault(values=values)


def anonymize_text(text: str) -> str:
    redacted, _vault = anonymize_with_vault(text)
    return redacted


CLOUD_PROVIDERS = frozenset({"openai", "gemini"})
LOCAL_PROVIDERS = frozenset({"local", "ollama"})
VALID_PROVIDERS = CLOUD_PROVIDERS | LOCAL_PROVIDERS


def prepare_text_for_llm(
    text: str,
    *,
    provider: str,
    anonymize_enabled: bool,
    require_anonymization_for_cloud: bool = True,
) -> str:
    provider = (provider or "openai").lower()
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Неподдерживаемый LLM-провайдер: {provider}")
    if provider in CLOUD_PROVIDERS:
        if require_anonymization_for_cloud and not anonymize_enabled:
            raise ValueError(
                "Отправка в облачный LLM без анонимизации запрещена. "
                "Включите анонимизацию в Настройках → Модели и AI."
            )
        if anonymize_enabled:
            redacted, _vault = anonymize_with_vault(text)
            return redacted
    return text
