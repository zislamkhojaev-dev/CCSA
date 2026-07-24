import { GripVertical, Settings } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, scoreBadge } from "../../api/client";
import type { DashboardWidget as WidgetConfig, WidgetMetricData } from "../../types/dashboard";

import type { DashboardFiltersState } from "../../utils/dashboardFilters";
import { buildDashboardQueryString, dashboardFiltersKey } from "../../utils/dashboardFilters";

type Props = {
  widget: WidgetConfig;
  filters: DashboardFiltersState;
  editing?: boolean;
  onEdit?: () => void;
  onRemove?: () => void;
  dragHandleProps?: {
    attributes: Record<string, unknown>;
    listeners: Record<string, unknown> | undefined;
  };
};

function BarChart({ series, unit }: { series: { label: string; value: number }[]; unit?: string }) {
  const max = Math.max(...series.map((s) => s.value), 1);
  return (
    <div className="dash-bars">
      {series.map((s) => (
        <div className="dash-bar-row" key={s.label}>
          <span className="dash-bar-label" title={s.label}>
            {s.label}
          </span>
          <div className="dash-bar-track">
            <div className="dash-bar-fill" style={{ width: `${(s.value / max) * 100}%` }} />
          </div>
          <span className="dash-bar-value">
            {s.value}
            {unit === "%" ? "%" : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

function ComparisonView({ data }: { data: WidgetMetricData }) {
  const cmp = data.comparison as {
    left?: { label: string; value: number; unit?: string };
    right?: { label: string; value: number; unit?: string };
  } | null;
  if (cmp?.left && cmp?.right) {
    return (
      <div className="dash-comparison">
        <div className="dash-comparison-col">
          <span className="dash-comparison-label">{cmp.left.label}</span>
          <strong className="dash-comparison-value">
            {cmp.left.value}
            {cmp.left.unit === "%" ? "%" : ""}
          </strong>
        </div>
        <span className="dash-comparison-vs">vs</span>
        <div className="dash-comparison-col">
          <span className="dash-comparison-label">{cmp.right.label}</span>
          <strong className="dash-comparison-value">
            {cmp.right.value}
            {cmp.right.unit === "%" ? "%" : ""}
          </strong>
        </div>
      </div>
    );
  }
  return <BarChart series={data.series} unit={data.unit ?? undefined} />;
}

function WidgetBody({ widget, data }: { widget: WidgetConfig; data: WidgetMetricData }) {
  const badge = widget.metric.includes("score") && data.value != null ? scoreBadge(data.value) : null;

  switch (widget.type) {
    case "chart":
      return <BarChart series={data.series} unit={data.unit ?? undefined} />;
    case "comparison":
      return <ComparisonView data={data} />;
    case "percent":
      return (
        <div className="dash-percent">
          <span className={`dash-kpi-value score-big ${badge ?? ""}`}>{data.formatted ?? "—"}</span>
          {data.comparison && (
            <span className="dash-percent-sub">
              {String((data.comparison as { numerator?: number }).numerator ?? "")} из{" "}
              {String((data.comparison as { denominator?: number }).denominator ?? "")}
            </span>
          )}
        </div>
      );
    case "stat":
      return (
        <div>
          <p className="dash-kpi-value">{data.formatted ?? "—"}</p>
          {data.stats && <p className="dash-widget-sub">Среднее за период</p>}
        </div>
      );
    case "kpi":
    case "count":
    default:
      return (
        <p className={`dash-kpi-value ${badge ? `score-big ${badge}` : ""}`}>
          {data.formatted ?? (data.value != null ? String(data.value) : "—")}
        </p>
      );
  }
}

export default function DashboardWidgetCard({
  widget,
  filters,
  editing,
  onEdit,
  onRemove,
  dragHandleProps,
}: Props) {
  const qs = buildDashboardQueryString(filters);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard-metric", widget.metric, ...dashboardFiltersKey(filters)],
    queryFn: () =>
      api.get<WidgetMetricData>(`/dashboard/metrics?metric=${encodeURIComponent(widget.metric)}&${qs}`),
  });

  return (
    <article className={`card dash-widget dash-widget--${widget.size}${editing ? " dash-widget--editing" : ""}`}>
      <header className="dash-widget-header">
        {editing && dragHandleProps && (
          <button
            type="button"
            className="btn btn-secondary btn-icon dash-drag-handle"
            {...dragHandleProps.attributes}
            {...dragHandleProps.listeners}
            aria-label="Перетащить"
          >
            <GripVertical size={14} />
          </button>
        )}
        <h3 title={widget.title}>{widget.title}</h3>
        {editing && (
          <div className="dash-widget-actions">
            {onEdit && (
              <button type="button" className="btn btn-secondary btn-icon" onClick={onEdit} aria-label="Настроить">
                <Settings size={14} />
              </button>
            )}
            {onRemove && (
              <button type="button" className="btn btn-icon btn-icon-danger" onClick={onRemove} aria-label="Удалить">
                ×
              </button>
            )}
          </div>
        )}
      </header>
      <div className="dash-widget-body">
        {isLoading && <p className="dash-widget-muted">Загрузка...</p>}
        {isError && <p className="text-error">Ошибка загрузки</p>}
        {data && <WidgetBody widget={widget} data={data} />}
      </div>
    </article>
  );
}
