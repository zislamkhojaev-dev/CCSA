from app.services.pii import anonymize_text, prepare_text_for_llm


def test_anonymize_phone():
    text = "Позвоните на +998901234567"
    result = anonymize_text(text)
    assert "[PII_DATA]" in result
    assert "998901234567" not in result


def test_anonymize_uz_phone_bot9b_style():
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
    try:
        prepare_text_for_llm("test", provider="openai", anonymize_enabled=False, require_anonymization_for_cloud=True)
        assert False, "Should raise"
    except ValueError as e:
        assert "анонимизац" in str(e).lower() or "запрещ" in str(e).lower()
