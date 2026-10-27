import pytest

from app.services.pii import PiiVault, anonymize_text, anonymize_with_vault, prepare_text_for_llm


def test_anonymize_phone():
    text = "Позвоните на +998901234567"
    result = anonymize_text(text)
    assert "[PII_DATA]" in result
    assert "998901234567" not in result


def test_anonymize_uz_phone_spaced():
    text = "Aloqa +998 90 123 45 67"
    result = anonymize_text(text)
    assert "[PII_DATA]" in result
    assert "123 45 67" not in result


def test_anonymize_pinfl():
    text = "PINFL 12345678901234"
    result = anonymize_text(text)
    assert "[PII_DATA]" in result
    assert "12345678901234" not in result


def test_cloud_gate_blocks_without_anonymization():
    with pytest.raises(ValueError, match=r"(?i)анонимизац|запрещ"):
        prepare_text_for_llm(
            "test",
            provider="openai",
            anonymize_enabled=False,
            require_anonymization_for_cloud=True,
        )


def test_local_provider_allows_without_anonymization():
    text = prepare_text_for_llm(
        "hello",
        provider="local",
        anonymize_enabled=False,
        require_anonymization_for_cloud=True,
    )
    assert text == "hello"


def test_local_phone_address_name_and_spoken_number():
    phone = anonymize_text("мой номер 90 123 45 67")
    assert "123 45 67" not in phone
    assert "[PII_DATA]" in phone

    spoken = anonymize_text("номер девять ноль один два три четыре пять шесть семь")
    assert "девять" not in spoken
    assert anonymize_text("bir daqiqa kutib turing") == "bir daqiqa kutib turing"

    named = anonymize_text("меня зовут Алишер Каримов")
    assert "Алишер" not in named
    assert "меня зовут" in named

    address = anonymize_text("живу на улица Навои, дом 12")
    assert "Навои" not in address
    assert "дом 12" not in address


def test_vault_roundtrip_does_not_keep_plaintext_in_the_blob():
    raw = "PINFL 12345678901234"
    redacted, vault = anonymize_with_vault(raw)
    assert "12345678901234" not in redacted
    blob = vault.encrypted()
    assert "12345678901234" not in blob
    restored = PiiVault.from_encrypted(blob).restore(redacted)
    assert restored == raw


def test_unknown_provider_is_rejected_before_cloud_dispatch():
    with pytest.raises(ValueError, match="Неподдерживаемый"):
        prepare_text_for_llm(
            "raw transcript",
            provider="typo-provider",
            anonymize_enabled=True,
        )
