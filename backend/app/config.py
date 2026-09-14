from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET_KEY = "dev-secret-key-change-in-production"
_DEV_FERNET_KEY = "dev-fernet-key-must-be-32-url-safe-b64="
_DEV_ADMIN_PASSWORD = "admin123"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        protected_namespaces=("model_",),
    )

    app_env: str = "development"
    secret_key: str = _DEV_SECRET_KEY
    fernet_encryption_key: str = Field(
        default=_DEV_FERNET_KEY,
        validation_alias="SETTINGS_ENCRYPTION_KEY",
    )

    database_url: str = "postgresql+asyncpg://ccsa:ccsa_secret@postgres:5432/ccsa"
    database_url_sync: str = "postgresql://ccsa:ccsa_secret@postgres:5432/ccsa"
    db_pool_timeout: int = 30
    db_connect_timeout: int = 10
    db_statement_timeout_ms: int = 30000

    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    redis_lock_ttl_sec: int = 1800

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "ccsa_minio"
    minio_secret_key: str = "ccsa_minio_secret"
    minio_bucket: str = "ccsa-audio"
    minio_secure: bool = False

    stt_service_url: str = "http://stt-service:8001"
    stt_model: str = "OvozifyLabs/whisper-small-uz-v1"
    stt_service_token: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_url: str = "https://generativelanguage.googleapis.com/v1beta"
    ollama_base_url: str = "http://host.docker.internal:11434"

    llm_timeout_sec: float = 45.0
    llm_timeout_long_sec: float = 120.0
    llm_timeout_cohort_sec: float = 300.0
    llm_max_retries: int = 3

    webitel_api_url: str = ""
    webitel_access_token: str = ""
    webitel_timeout_sec: float = 15.0
    webitel_timeout_list_sec: float = 60.0
    webitel_timeout_download_sec: float = 120.0
    webitel_max_retries: int = 3
    webitel_db_connect_timeout: int = 10

    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    cookie_access_max_age: int = 3600
    cookie_refresh_max_age: int = 604800

    cors_origins: str = ""
    log_level: str = "INFO"

    seed_admin_login: str = "admin"
    seed_admin_password: str = _DEV_ADMIN_PASSWORD

    research_max_calls: int = 200
    filter_options_limit: int = 500
    idempotency_ttl_hours: int = 24

    feature_research: bool = True
    feature_playground: bool = True
    feature_webitel_sync: bool = True
    feature_dashboard_constructor: bool = True

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self):
        if self.app_env != "production":
            return self
        missing: list[str] = []
        if self.secret_key == _DEV_SECRET_KEY:
            missing.append("SECRET_KEY")
        if self.fernet_encryption_key == _DEV_FERNET_KEY:
            missing.append("SETTINGS_ENCRYPTION_KEY")
        if self.seed_admin_password == _DEV_ADMIN_PASSWORD:
            missing.append("SEED_ADMIN_PASSWORD")
        if not self.cors_origins.strip():
            missing.append("CORS_ORIGINS")
        if missing:
            raise ValueError(
                "Production refuses unsafe defaults. Set: " + ", ".join(missing)
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        if self.app_env == "development":
            return ["*"]
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def cookie_secure(self) -> bool:
        return self.app_env != "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
