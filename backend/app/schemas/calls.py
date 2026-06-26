from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.tags import TagOut


class CallListItem(BaseModel):
    id: int
    call_uuid: UUID
    operator_name: str | None
    direction: str | None
    duration: int | None
    client_number: str | None
    call_timestamp: datetime | None
    status: str
    total_score: int | None
    is_violation: bool | None

    model_config = {"from_attributes": True}


class TranscriptionOut(BaseModel):
    id: int
    full_text: str | None
    utterances: list | dict | None
    model_name: str | None

    model_config = {"from_attributes": True}


class AnalysisOut(BaseModel):
    id: int
    total_score: int | None
    is_violation: bool
    summary: str | None
    client_pains: str | None
    call_outcome: str | None
    criteria_results: dict | None
    llm_model: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CallDetailOut(BaseModel):
    id: int
    call_uuid: UUID
    operator_id: int | None
    operator_name: str | None
    scenario_id: int | None
    scenario_name: str | None
    direction: str | None
    duration: int | None
    client_number: str | None
    call_timestamp: datetime | None
    status: str
    error_message: str | None
    audio_url: str | None
    tags: list[TagOut]
    transcriptions: list[TranscriptionOut]
    analysis_results: list[AnalysisOut]
    notes: list["NoteOut"]


class CallBulkDelete(BaseModel):
    ids: list[int] = Field(min_length=1)


class CallTagsUpdate(BaseModel):
    tag_ids: list[int]


class NoteCreate(BaseModel):
    text: str


class NoteOut(BaseModel):
    id: int
    text: str
    user_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


CallDetailOut.model_rebuild()
