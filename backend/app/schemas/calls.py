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
    topic: str | None = None
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


class CallStatusOut(BaseModel):
    id: int
    status: str
    error_message: str | None = None

    model_config = {"from_attributes": True}


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


class CallExportFilters(BaseModel):
    status_filter: str | None = None
    operator_match: str | None = None
    operator_value: str | None = None
    client_match: str | None = None
    client_value: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    duration_op: str | None = None
    duration_value: int | None = None
    score_op: str | None = None
    score_value: int | None = None
    tag_id: int | None = None


class CallExportSyncBody(BaseModel):
    format: str = Field(pattern="^(json|csv)$")
    ids: list[int] = Field(min_length=1)


class CallExportJobCreate(BaseModel):
    format: str = Field(pattern="^(json|csv)$")
    filters: CallExportFilters = Field(default_factory=CallExportFilters)


class CallExportJobOut(BaseModel):
    id: int
    format: str
    status: str
    message: str | None = None
    row_count: int = 0
    error_message: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


CallDetailOut.model_rebuild()
