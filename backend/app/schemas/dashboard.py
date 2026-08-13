from pydantic import BaseModel, Field, field_validator, model_validator


class ScoreBucket(BaseModel):
    label: str
    count: int


class DashboardSummary(BaseModel):
    total_calls: int
    analyzed_calls: int
    avg_score: float | None
    violations_count: int
    calls_today: int
    score_distribution: list[ScoreBucket]
    top_violations: list[dict]


class MetricSeriesPoint(BaseModel):
    label: str
    value: float
    value_secondary: float | None = None


class WidgetMetricResponse(BaseModel):
    metric: str
    kind: str
    label: str
    value: float | None = None
    formatted: str | None = None
    unit: str | None = None
    target: float | None = None
    series: list[MetricSeriesPoint] = Field(default_factory=list)
    comparison: dict | None = None
    stats: dict | None = None
    matrix: dict | None = None


class WidgetMetricsBatchIn(BaseModel):
    metrics: list[str] = Field(min_length=1, max_length=40)
    period_days: int = Field(default=30, ge=1, le=365)
    date_from: str | None = None
    date_to: str | None = None
    direction: str | None = None
    operator_ids: list[int] | None = None
    scenario_id: int | None = None


class WidgetMetricsBatchOut(BaseModel):
    items: dict[str, WidgetMetricResponse]


class DashboardWidgetConfig(BaseModel):
    id: str
    type: str
    title: str
    metric: str
    compare_metric: str | None = None
    width: int = Field(default=2, ge=1, le=4)
    height: int = Field(default=1, ge=1, le=2)
    size: str | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_size(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if "width" not in payload or "height" not in payload:
            legacy = payload.get("size") or "medium"
            mapping = {
                "small": (1, 1),
                "medium": (2, 1),
                "large": (4, 2),
            }
            width, height = mapping.get(str(legacy), (2, 1))
            payload.setdefault("width", width)
            payload.setdefault("height", height)
        return payload

    @field_validator("width")
    @classmethod
    def clamp_width(cls, value: int) -> int:
        return max(1, min(4, int(value)))

    @field_validator("height")
    @classmethod
    def clamp_height(cls, value: int) -> int:
        return 1 if int(value) < 2 else 2


class DashboardLayoutOut(BaseModel):
    widgets: list[DashboardWidgetConfig] = Field(default_factory=list)


class DashboardLayoutUpdate(BaseModel):
    widgets: list[DashboardWidgetConfig]
