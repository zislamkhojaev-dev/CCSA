import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.fernet_encryption_key.encode()
    digest = hashlib.sha256(key).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_value(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()
