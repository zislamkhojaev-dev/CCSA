from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        protected_namespaces=("model_",),
    )

    app_env: str = "development"
    secret_key: str = "dev-secret-key-change-in-production"
    fernet_encryption_key: str = Field(
        default="dev-fernet-key-must-be-32-url-safe-b64=",
        validation_alias="SETTINGS_ENCRYPTION_KEY",
    )

    database_url: str = "postgresql+asyncpg://ccsa:ccsa_secret@postgres:5432/ccsa"
    database_url_sync: str = "postgresql://ccsa:ccsa_secret@postgres:5432/ccsa"

    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "ccsa_minio"
    minio_secret_key: str = "ccsa_minio_secret"
    minio_bucket: str = "ccsa-audio"
    minio_secure: bool = False

    stt_service_url: str = "http://stt-service:8001"
    stt_model: str = "OvozifyLabs/whisper-small-uz-v1"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    webitel_api_url: str = ""
    webitel_access_token: str = ""

    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    seed_admin_login: str = "admin"
    seed_admin_password: str = "admin123"

    research_max_calls: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
