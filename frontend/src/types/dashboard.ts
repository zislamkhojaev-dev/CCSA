export type WidgetType = "kpi" | "chart" | "comparison" | "count" | "stat" | "percent";

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

export type WidgetMetricData = {
  metric: string;
  kind: string;
  label: string;
  value?: number | null;
  formatted?: string | null;
  unit?: string | null;
  series: MetricSeriesPoint[];
  comparison?: Record<string, unknown> | null;
  stats?: Record<string, unknown> | null;
};

export const WIDGET_TYPES: { value: WidgetType; label: string }[] = [
  { value: "kpi", label: "KPI / значение" },
  { value: "count", label: "Количество" },
  { value: "stat", label: "Статистика" },
  { value: "percent", label: "Процент" },
  { value: "chart", label: "График" },
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
];

export const DEFAULT_LAYOUT: DashboardLayout = {
  widgets: [
    { id: "w1", type: "count", title: "Всего звонков", metric: "calls_total", size: "small" },
    { id: "w2", type: "count", title: "Проанализировано", metric: "calls_analyzed", size: "small" },
    { id: "w3", type: "kpi", title: "Средний балл", metric: "score_avg", size: "small" },
    { id: "w4", type: "count", title: "Нарушения", metric: "violations_count", size: "small" },
    { id: "w5", type: "count", title: "Звонков сегодня", metric: "calls_today", size: "small" },
    {
      id: "w6",
      type: "chart",
      title: "Распределение оценок",
      metric: "score_distribution",
      size: "large",
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
  return "";
}
