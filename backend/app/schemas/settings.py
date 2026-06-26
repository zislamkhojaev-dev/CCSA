from pydantic import BaseModel, Field


class SettingsModelsOut(BaseModel):
    asr_provider: str
    asr_model: str
    asr_diarization_method: str
    asr_api_url: str
    asr_api_key_set: bool
    asr_max_parallel: int = 1
    asr_http_timeout_sec: int = 600
    playground_sequential: bool = True
    celery_worker_concurrency: int = 1
    llm_provider: str
    llm_model: str
    pii_anonymization: bool
    openai_api_key_set: bool
    gemini_api_key_set: bool
    ollama_base_url: str


class SettingsUpdate(BaseModel):
    asr_provider: str | None = None
    asr_model: str | None = None
    asr_diarization_method: str | None = None
    asr_api_url: str | None = None
    asr_api_key: str | None = None
    asr_max_parallel: int | None = None
    asr_http_timeout_sec: int | None = None
    playground_sequential: bool | None = None
    celery_worker_concurrency: int | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    pii_anonymization: bool | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str | None = None


class WebitelSettings(BaseModel):
    api_url: str = ""
    access_token: str | None = None
    sync_frequency: str = "30min"
    sync_cron: str = "*/30 * * * *"
    sync_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    sync_time_from: str = "09:00"
    sync_time_to: str = "18:00"


class WebitelDbSettings(BaseModel):
    host: str = ""
    port: int = 5432
    database: str = "webitel"
    user: str = ""
    password: str | None = None


class AutomationRuleOut(BaseModel):
    id: int
    is_enabled: bool
    schedule_cron: str
    batch_size: int
    active_days: list
    time_from: str | None
    time_to: str | None
    default_scenario_id: int | None

    model_config = {"from_attributes": True}


class AutomationRuleUpdate(BaseModel):
    is_enabled: bool | None = None
    schedule_cron: str | None = None
    batch_size: int | None = None
    active_days: list[int] | None = None
    time_from: str | None = None
    time_to: str | None = None
    default_scenario_id: int | None = None
