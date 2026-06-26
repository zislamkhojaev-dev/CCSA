from datetime import datetime

from pydantic import BaseModel, Field


class CriterionCreate(BaseModel):
    key: str
    name: str
    weight_percent: int = 10
    max_score: int = 10
    prompt: str = ""
    sort_order: int = 0


class CriterionOut(CriterionCreate):
    id: int

    model_config = {"from_attributes": True}


class ScenarioCreate(BaseModel):
    name: str
    system_prompt: str = ""
    llm_model: str = "gpt-4o-mini"
    is_active: bool = True
    criteria: list[CriterionCreate] = Field(default_factory=list)


class ScenarioUpdate(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    llm_model: str | None = None
    is_active: bool | None = None
    criteria: list[CriterionCreate] | None = None


class ScenarioOut(BaseModel):
    id: int
    name: str
    system_prompt: str
    llm_model: str
    is_active: bool
    updated_at: datetime
    criteria: list[CriterionOut] = []
    criteria_count: int = 0

    model_config = {"from_attributes": True}
