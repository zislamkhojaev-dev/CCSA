from datetime import UTC, datetime, timedelta
import uuid

import bcrypt
import jwt

from app.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _create_token(subject: int | str, token_type: str, expires_delta: timedelta) -> str:
    issued_at = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(subject),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + expires_delta,
            "jti": str(uuid.uuid4()),
            "type": token_type,
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def create_access_token(subject: int | str) -> str:
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: int | str) -> str:
    return _create_token(
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "iss", "aud", "iat", "nbf", "exp", "jti", "type"]},
        )
    except jwt.PyJWTError:
        return None
