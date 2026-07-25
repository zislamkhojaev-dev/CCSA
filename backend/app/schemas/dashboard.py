from pydantic import BaseModel, Field


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


class DashboardWidgetConfig(BaseModel):
    id: str
    type: str
    title: str
    metric: str
    compare_metric: str | None = None
    size: str = "medium"


class DashboardLayoutOut(BaseModel):
    widgets: list[DashboardWidgetConfig] = Field(default_factory=list)


class DashboardLayoutUpdate(BaseModel):
    widgets: list[DashboardWidgetConfig]
