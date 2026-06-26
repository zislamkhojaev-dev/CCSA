from datetime import datetime

from pydantic import BaseModel


class PlaygroundJobCreate(BaseModel):
    scenario_id: int | None = None
    use_scenario_prompt: bool = True
    custom_prompt: str | None = None


class PlaygroundFileOut(BaseModel):
    id: int
    filename: str
    status: str
    error_message: str | None
    audio_url: str | None = None
    transcription: dict | None = None
    analysis: dict | None = None

    model_config = {"from_attributes": True}


class PlaygroundJobOut(BaseModel):
    id: int
    status: str
    scenario_id: int | None
    created_at: datetime
    files: list[PlaygroundFileOut] = []

    model_config = {"from_attributes": True}
