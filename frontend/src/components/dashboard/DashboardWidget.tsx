import { GripVertical, Settings } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, scoreBadge } from "../../api/client";
import type {
  DashboardWidget as WidgetConfig,
  MatrixCell,
  MetricMatrix,
  MetricSeriesPoint,
  WidgetMetricData,
} from "../../types/dashboard";

import type { DashboardFiltersState } from "../../utils/dashboardFilters";
import { buildDashboardQueryString, dashboardFiltersKey } from "../../utils/dashboardFilters";

function useQualityThresholds() {
  const { data } = useQuery({
    queryKey: ["settings-quality"],
    queryFn: () =>
      api.get<{ threshold_good: number; threshold_mid: number; target: number }>("/settings/quality"),
    staleTime: 5 * 60 * 1000,
  });
  return {
    good: data?.threshold_good ?? 80,
    mid: data?.threshold_mid ?? 50,
    target: data?.target ?? 85,
  };
}

function scoreColorVar(v: number, good: number, mid: number): string {
  if (v >= good) return "var(--green)";
  if (v >= mid) return "var(--yellow)";
  return "var(--red)";
}

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

function RankedBars({
  series,
  unit,
  colorByScore,
}: {
  series: MetricSeriesPoint[];
  unit?: string;
  colorByScore?: boolean;
}) {
  const { good, mid } = useQualityThresholds();
  const isPct = unit === "%";
  const max = isPct ? 100 : Math.max(...series.map((s) => s.value), 1);
  if (!series.length) return <p className="dash-widget-muted">Нет данных</p>;
  return (
    <div className="dash-bars">
      {series.map((s, i) => {
        const color = colorByScore && isPct ? scoreColorVar(s.value, good, mid) : "var(--primary)";
        return (
          <div className="dash-bar-row" key={`${s.label}-${i}`}>
            <span className="dash-bar-label" title={s.label}>
              {s.label}
            </span>
            <div className="dash-bar-track">
              <div className="dash-bar-fill" style={{ width: `${(s.value / max) * 100}%`, background: color }} />
            </div>
            <span className="dash-bar-value">
              {s.value}
              {isPct ? "%" : ""}
              {s.value_secondary != null && <span className="dash-bar-sub"> · {s.value_secondary}</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function TrendChart({
  series,
  unit,
  target,
}: {
  series: MetricSeriesPoint[];
  unit?: string;
  target?: number | null;
}) {
  if (!series.length) return <p className="dash-widget-muted">Нет данных</p>;
  const w = 100;
  const h = 40;
  const isPct = unit === "%";
  const values = series.map((s) => s.value);
  const maxV = isPct ? 100 : Math.max(...values, 1);
  const range = maxV || 1;
  const stepX = series.length > 1 ? w / (series.length - 1) : 0;
  const points = series
    .map((s, i) => {
      const x = series.length > 1 ? i * stepX : w / 2;
      const y = h - (s.value / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const targetY = target != null ? h - (target / range) * h : null;
  return (
    <div className="dash-trend">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="dash-trend-svg">
        {targetY != null && targetY >= 0 && targetY <= h && (
          <line x1="0" y1={targetY} x2={w} y2={targetY} className="dash-trend-target" strokeDasharray="3 2" />
        )}
        <polyline points={points} className="dash-trend-line" fill="none" />
      </svg>
      <div className="dash-trend-foot">
        <span>{series[0].label}</span>
        {target != null && (
          <span className="dash-trend-target-label">
            цель {target}
            {isPct ? "%" : ""}
          </span>
        )}
        <span>{series[series.length - 1].label}</span>
      </div>
    </div>
  );
}

function Heatmap({ matrix }: { matrix: MetricMatrix }) {
  const { good, mid } = useQualityThresholds();
  const isPct = matrix.unit === "%";
  let maxCount = 1;
  if (!isPct) {
    for (const row of matrix.cells) {
      for (const c of row) {
        if (c && c.value > maxCount) maxCount = c.value;
      }
    }
  }
  const cellColor = (c: MatrixCell): string => {
    if (!c) return "transparent";
    if (isPct) {
      const base = c.value >= good ? "var(--green)" : c.value >= mid ? "var(--yellow)" : "var(--red)";
      return `color-mix(in srgb, ${base} 55%, transparent)`;
    }
    const intensity = Math.round((c.value / maxCount) * 100);
    return `color-mix(in srgb, var(--primary) ${Math.max(4, intensity)}%, transparent)`;
  };
  if (!matrix.rows.length || !matrix.cols.length) {
    return <p className="dash-widget-muted">Нет данных</p>;
  }
  return (
    <div className="dash-heatmap-scroll">
      <table className="dash-heatmap">
        <thead>
          <tr>
            <th className="dash-heatmap-corner" />
            {matrix.cols.map((c, i) => (
              <th key={i} title={c.label}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map((r, ri) => (
            <tr key={ri}>
              <th title={r.label}>{r.label}</th>
              {matrix.cells[ri]?.map((cell, ci) => (
                <td
                  key={ci}
                  style={{ background: cellColor(cell) }}
                  title={
                    cell
                      ? `${cell.value}${isPct ? "%" : ""}${cell.count ? ` · ${cell.count}` : ""}`
                      : "нет данных"
                  }
                >
                  {cell ? (isPct ? Math.round(cell.value) : cell.value || "") : ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WidgetSkeleton({ type }: { type: WidgetConfig["type"] }) {
  if (type === "chart" || type === "bars") {
    return (
      <div className="dash-skel dash-skel-bars" aria-label="Загрузка" aria-busy="true">
        {[72, 48, 88, 40, 62].map((w, i) => (
          <span key={i} className="dash-skel-block dash-skel-shimmer" style={{ width: `${w}%` }} />
        ))}
      </div>
    );
  }
  if (type === "trend") {
    return <div className="dash-skel-block dash-skel-shimmer dash-skel-trend" aria-busy="true" />;
  }
  if (type === "heatmap") {
    return (
      <div className="dash-skel-grid" aria-busy="true">
        {Array.from({ length: 32 }).map((_, i) => (
          <span key={i} className="dash-skel-block dash-skel-shimmer dash-skel-cell" />
        ))}
      </div>
    );
  }
  if (type === "comparison") {
    return (
      <div className="dash-skel-compare" aria-busy="true">
        <span className="dash-skel-block dash-skel-shimmer" />
        <span className="dash-skel-block dash-skel-shimmer" />
      </div>
    );
  }
  return <div className="dash-skel-block dash-skel-shimmer dash-skel-kpi" aria-busy="true" />;
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
    case "bars":
      return (
        <RankedBars
          series={data.series}
          unit={data.unit ?? undefined}
          colorByScore={data.unit === "%"}
        />
      );
    case "trend":
      return <TrendChart series={data.series} unit={data.unit ?? undefined} target={data.target} />;
    case "heatmap":
      return data.matrix ? (
        <Heatmap matrix={data.matrix} />
      ) : (
        <p className="dash-widget-muted">Нет данных</p>
      );
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
        {isLoading && <WidgetSkeleton type={widget.type} />}
        {isError && <p className="text-error">Ошибка загрузки</p>}
        {!isLoading && data && <WidgetBody widget={widget} data={data} />}
      </div>
    </article>
  );
}
