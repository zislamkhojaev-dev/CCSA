from app.core.security import create_access_token, create_refresh_token, decode_token


def test_access_token_has_required_claims():
    payload = decode_token(create_access_token(42))

    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["iss"] == "ccsa"
    assert payload["aud"] == "ccsa-web"
    assert payload["jti"]


def test_refresh_token_type_is_distinct():
    payload = decode_token(create_refresh_token(42))

    assert payload is not None
    assert payload["type"] == "refresh"


def test_token_with_wrong_audience_is_rejected():
    token = create_access_token(42)
    from app.core.security import settings

    original = settings.jwt_audience
    settings.jwt_audience = "different-audience"
    try:
        assert decode_token(token) is None
    finally:
        settings.jwt_audience = original
