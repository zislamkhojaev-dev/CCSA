export type WidgetType =
  | "kpi"
  | "chart"
  | "comparison"
  | "count"
  | "stat"
  | "percent"
  | "bars"
  | "trend"
  | "heatmap";

export type WidgetSize = "small" | "medium" | "large";

export type DashboardWidget = {
  id: string;
  type: WidgetType;
  title: string;
  metric: string;
  compare_metric?: string | null;
  size: WidgetSize;
};

export type DashboardLayout = {
  widgets: DashboardWidget[];
};

export type MetricSeriesPoint = {
  label: string;
  value: number;
  value_secondary?: number | null;
};

export type MatrixCell = { value: number; count?: number } | null;

export type MetricMatrix = {
  rows: { label: string; key?: string }[];
  cols: { label: string; key?: string }[];
  cells: MatrixCell[][];
  unit?: string;
};

export type WidgetMetricData = {
  metric: string;
  kind: string;
  label: string;
  value?: number | null;
  formatted?: string | null;
  unit?: string | null;
  target?: number | null;
  series: MetricSeriesPoint[];
  comparison?: Record<string, unknown> | null;
  stats?: Record<string, unknown> | null;
  matrix?: MetricMatrix | null;
};

export const WIDGET_TYPES: { value: WidgetType; label: string }[] = [
  { value: "kpi", label: "KPI / значение" },
  { value: "count", label: "Количество" },
  { value: "stat", label: "Статистика" },
  { value: "percent", label: "Процент" },
  { value: "chart", label: "График (столбцы)" },
  { value: "bars", label: "Рейтинг (горизонтальные бары)" },
  { value: "trend", label: "Динамика (линия + цель)" },
  { value: "heatmap", label: "Тепловая таблица" },
  { value: "comparison", label: "Сравнение" },
];

export const METRIC_OPTIONS: { value: string; label: string; category: string }[] = [
  { value: "calls_total", label: "Всего звонков", category: "Звонки" },
  { value: "calls_today", label: "Звонков сегодня", category: "Звонки" },
  { value: "calls_analyzed", label: "Проанализировано", category: "Звонки" },
  { value: "calls_pending", label: "В очереди", category: "Звонки" },
  { value: "calls_by_day", label: "Звонки по дням", category: "Звонки" },
  { value: "comparison_calls_analyzed", label: "Звонки vs проанализировано", category: "Звонки" },
  { value: "score_avg", label: "Средний балл", category: "Оценки" },
  { value: "score_distribution", label: "Распределение оценок", category: "Оценки" },
  { value: "violations_count", label: "Нарушения", category: "Оценки" },
  { value: "percent_high_score", label: "Доля оценок >80%", category: "Оценки" },
  { value: "percent_violations", label: "Доля нарушений", category: "Оценки" },
  { value: "comparison_score_violations", label: "Балл vs нарушения", category: "Оценки" },
  { value: "duration_avg", label: "Средняя длительность", category: "Длительность" },
  { value: "duration_total", label: "Суммарная длительность", category: "Длительность" },
  { value: "duration_distribution", label: "Распределение длительности", category: "Длительность" },
  { value: "operators_by_calls", label: "Топ операторов (звонки)", category: "Операторы" },
  { value: "operators_by_score", label: "Топ операторов (балл)", category: "Операторы" },
  { value: "percent_analyzed", label: "Доля проанализированных", category: "Звонки" },
  { value: "coverage", label: "Покрытие оценкой", category: "Оценки" },
  { value: "criteria_pass_rate", label: "Проседающие критерии", category: "Критерии" },
  { value: "criteria_operator_heatmap", label: "Критерии × операторы", category: "Критерии" },
  { value: "score_by_day", label: "Динамика среднего балла", category: "Оценки" },
  { value: "operators_top_best", label: "Топ-5 лучших операторов", category: "Операторы" },
  { value: "operators_top_worst", label: "Топ-5 худших операторов", category: "Операторы" },
  { value: "topics_distribution", label: "Классификация тем", category: "Темы" },
  { value: "score_by_topic", label: "Качество по темам", category: "Темы" },
  { value: "calls_heatmap_hour_day", label: "Пиковые часы (час × день)", category: "Нагрузка" },
];

/**
 * Allowed visualization types per metric. The first entry is the default.
 * Constrains the widget editor so impossible metric/visualization combos can't be built.
 */
export const METRIC_ALLOWED_TYPES: Record<string, WidgetType[]> = {
  calls_total: ["count", "kpi"],
  calls_today: ["count", "kpi"],
  calls_analyzed: ["count", "kpi"],
  calls_pending: ["count", "kpi"],
  violations_count: ["count", "kpi"],
  score_avg: ["kpi"],
  percent_analyzed: ["percent"],
  percent_violations: ["percent"],
  percent_high_score: ["percent"],
  coverage: ["percent"],
  duration_avg: ["stat"],
  duration_total: ["stat"],
  score_distribution: ["chart"],
  duration_distribution: ["chart"],
  calls_by_day: ["trend", "chart"],
  score_by_day: ["trend"],
  operators_by_calls: ["bars", "chart"],
  operators_by_score: ["bars"],
  operators_top_best: ["bars"],
  operators_top_worst: ["bars"],
  criteria_pass_rate: ["bars"],
  topics_distribution: ["bars", "chart"],
  score_by_topic: ["bars"],
  comparison_calls_analyzed: ["comparison"],
  comparison_score_violations: ["comparison"],
  criteria_operator_heatmap: ["heatmap"],
  calls_heatmap_hour_day: ["heatmap"],
};

export function allowedWidgetTypes(metric: string): WidgetType[] {
  return METRIC_ALLOWED_TYPES[metric] ?? ["kpi"];
}

export function defaultWidgetType(metric: string): WidgetType {
  return allowedWidgetTypes(metric)[0];
}

/** Metrics whose bar labels are long names (topics, criteria, operators). */
export const CATEGORY_BAR_METRICS = new Set([
  "topics_distribution",
  "score_by_topic",
  "criteria_pass_rate",
  "operators_by_calls",
  "operators_by_score",
  "operators_top_best",
  "operators_top_worst",
]);

export function usesCategoryBars(metric: string, type: WidgetType): boolean {
  return type === "bars" && CATEGORY_BAR_METRICS.has(metric);
}

/**
 * Recommended grid footprint per metric + visualization.
 * KPI/scalars → small; trends/comparisons/distributions → medium; lists/heatmaps → large.
 */
export function suggestedWidgetSize(metric: string, type?: WidgetType): WidgetSize {
  const visualization = type ?? defaultWidgetType(metric);

  if (visualization === "heatmap") return "large";

  if (visualization === "kpi" || visualization === "count" || visualization === "percent") {
    return "small";
  }

  if (visualization === "stat") {
    return metric === "duration_total" ? "medium" : "small";
  }

  if (visualization === "comparison") return "medium";

  if (metric === "calls_by_day") {
    return visualization === "trend" ? "large" : "medium";
  }

  if (metric === "score_by_day") return "medium";

  if (metric === "score_distribution" || metric === "duration_distribution") {
    return "medium";
  }

  if (
    metric === "topics_distribution" ||
    metric === "score_by_topic" ||
    metric === "criteria_pass_rate"
  ) {
    return "large";
  }

  if (
    metric === "operators_by_calls" ||
    metric === "operators_by_score" ||
    metric === "operators_top_best" ||
    metric === "operators_top_worst"
  ) {
    return "medium";
  }

  if (visualization === "trend" || visualization === "chart" || visualization === "bars") {
    return "medium";
  }

  return "small";
}

export const WIDGET_SIZE_LABELS: Record<WidgetSize, string> = {
  small: "Малый — KPI / одно число",
  medium: "Средний — график или рейтинг",
  large: "Большой — списки, темы, heatmap",
};

/** Human-readable spec for widget editor hints. */
export function widgetSizeHint(metric: string, type: WidgetType): string {
  return WIDGET_SIZE_LABELS[suggestedWidgetSize(metric, type)];
}

export const DEFAULT_LAYOUT: DashboardLayout = {
  widgets: [
    { id: "w1", type: "count", title: "Всего звонков", metric: "calls_total", size: "small" },
    { id: "w2", type: "count", title: "Проанализировано", metric: "calls_analyzed", size: "small" },
    { id: "w3", type: "kpi", title: "Средний балл", metric: "score_avg", size: "small" },
    { id: "w4", type: "count", title: "Нарушения", metric: "violations_count", size: "small" },
    { id: "w5", type: "percent", title: "Покрытие", metric: "coverage", size: "small" },
    {
      id: "w6",
      type: "trend",
      title: "Звонки по дням",
      metric: "calls_by_day",
      size: "large",
    },
    {
      id: "w7",
      type: "chart",
      title: "Распределение оценок",
      metric: "score_distribution",
      size: "medium",
    },
  ],
};

export function newWidgetId(): string {
  return `w_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

/** CSS class for grid footprint on `.dash-sortable-item` (direct grid child). */
export function widgetGridSizeClass(size: WidgetSize): string {
  if (size === "large") return "dash-sortable-item--large";
  if (size === "medium") return "dash-sortable-item--medium";
  return "dash-sortable-item--small";
}
