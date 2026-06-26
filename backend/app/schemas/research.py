from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.tags import TagOut


class ResearchFilters(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    direction: str | None = Field(None, description="inbound | outbound")
    operator_id: int | None = None
    queue: str | None = Field(None, description="Очередь / команда оператора (operators.team_name)")
    tag_id: int | None = Field(None, description="ID тега из справочника")
    tag: str | None = Field(None, description="Устар.: название тега (для сохранённых фильтров)")
    score_op: str | None = Field(None, pattern="^(eq|lt|gt)$")
    score_value: int | None = Field(None, ge=0, le=100)


class ResearchFilterOptionsOut(BaseModel):
    queues: list[str]
    tags: list[TagOut]


class ResearchPreviewIn(BaseModel):
    filters: ResearchFilters


class ResearchPreviewOut(BaseModel):
    count: int
    max_calls: int


class ResearchCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1)
    filters: ResearchFilters


class ResearchListItem(BaseModel):
    id: int
    title: str
    status: str
    call_count: int
    filters_json: dict
    user_name: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ResearchDetailOut(BaseModel):
    id: int
    title: str
    prompt: str
    filters_json: dict
    status: str
    call_count: int
    call_ids: list[int] | None
    llm_model: str | None
    report_markdown: str | None
    error_message: str | None
    user_name: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}
