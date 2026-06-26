import logging
import re

logger = logging.getLogger(__name__)

# Same patterns as chatagent-naive/bot9b.py PII_PATTERNS
PII_PATTERNS: list[dict[str, str]] = [
    {
        "entity": "PHONE_NUMBER",
        "regex": r"\+998\s?(?:90|91|93|94|95|97|98|99|33|88)\s?\d{3}\s?\d{2}\s?\d{2}",
    },
    {"entity": "PASSPORT", "regex": r"[A-Z]{2}\d{7}"},
    {"entity": "CREDIT_CARD", "regex": r"\b\d{4}\s?-?\d{4}\s?-?\d{4}\s?-?\d{4}\b"},
    {"entity": "UZBEK_PINFL", "regex": r"\b\d{14}\b"},
    {
        "entity": "EMAIL_ADDRESS",
        "regex": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    },
]

REPLACEMENT = "[PII_DATA]"


def anonymize_text(text: str) -> str:
    if not text:
        return text
    result = text
    for pattern in PII_PATTERNS:
        regex = pattern["regex"]
        matches = re.findall(regex, result)
        if matches:
            logger.debug("PII %s matched %d time(s)", pattern["entity"], len(matches))
        result = re.sub(regex, REPLACEMENT, result)
    return result


CLOUD_PROVIDERS = frozenset({"openai", "gemini"})


def prepare_text_for_llm(
    text: str,
    *,
    provider: str,
    anonymize_enabled: bool,
    require_anonymization_for_cloud: bool = True,
) -> str:
    provider = (provider or "openai").lower()
    if provider in CLOUD_PROVIDERS:
        if require_anonymization_for_cloud and not anonymize_enabled:
            raise ValueError(
                "Отправка в облачный LLM без анонимизации запрещена. "
                "Включите анонимизацию в Настройках → Модели и AI."
            )
        if anonymize_enabled:
            return anonymize_text(text)
    return text
