const STORAGE_KEY = "ccsa-dashboard-filters";

export const DASHBOARD_PERIOD_PRESETS = [7, 30, 90] as const;
export type DashboardPeriodPreset = (typeof DASHBOARD_PERIOD_PRESETS)[number];
export type DashboardPeriodMode = `${DashboardPeriodPreset}` | "custom";
export type DashboardDirection = "" | "inbound" | "outbound";

export type OperatorFilterItem = { id: number; name: string };

export interface DashboardFiltersState {
  periodMode: DashboardPeriodMode;
  dateFrom: string;
  dateTo: string;
  direction: DashboardDirection;
  operators: OperatorFilterItem[];
}

const DEFAULT_FILTERS: DashboardFiltersState = {
  periodMode: "30",
  dateFrom: "",
  dateTo: "",
  direction: "",
  operators: [],
};

export function getDefaultDashboardFilters(): DashboardFiltersState {
  return { ...DEFAULT_FILTERS, operators: [] };
}

export function loadDashboardFilters(): DashboardFiltersState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return getDefaultDashboardFilters();
    const data = JSON.parse(raw) as Partial<DashboardFiltersState>;
    const periodMode = String(data.periodMode ?? "30") as DashboardPeriodMode;
    const validMode =
      periodMode === "custom" ||
      DASHBOARD_PERIOD_PRESETS.includes(Number(periodMode) as DashboardPeriodPreset)
        ? periodMode
        : "30";
    const direction = data.direction === "inbound" || data.direction === "outbound" ? data.direction : "";
    const operators = Array.isArray(data.operators)
      ? data.operators.filter(
          (o): o is OperatorFilterItem =>
            !!o && typeof o.id === "number" && typeof o.name === "string",
        )
      : [];
    return {
      periodMode: validMode,
      dateFrom: typeof data.dateFrom === "string" ? data.dateFrom : "",
      dateTo: typeof data.dateTo === "string" ? data.dateTo : "",
      direction,
      operators,
    };
  } catch {
    return getDefaultDashboardFilters();
  }
}

export function saveDashboardFilters(filters: DashboardFiltersState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
  } catch {
    /* ignore */
  }
}

/** Stable key for react-query cache invalidation. */
export function dashboardFiltersKey(filters: DashboardFiltersState): unknown[] {
  return [
    filters.periodMode,
    filters.dateFrom,
    filters.dateTo,
    filters.direction,
    filters.operators
      .map((o) => o.id)
      .sort((a, b) => a - b)
      .join(","),
  ];
}

export function buildDashboardQueryString(filters: DashboardFiltersState): string {
  const params = new URLSearchParams();
  if (filters.periodMode === "custom") {
    if (filters.dateFrom) params.set("date_from", filters.dateFrom);
    if (filters.dateTo) params.set("date_to", filters.dateTo);
    if (!filters.dateFrom && !filters.dateTo) {
      params.set("period_days", "30");
    }
  } else {
    params.set("period_days", filters.periodMode);
  }
  if (filters.direction) params.set("direction", filters.direction);
  for (const op of filters.operators) {
    params.append("operator_ids", String(op.id));
  }
  return params.toString();
}

const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

export async function downloadDashboardExport(
  filters: DashboardFiltersState,
  format: "json" | "csv",
): Promise<void> {
  const qs = buildDashboardQueryString(filters);
  const url = `${API_BASE}/dashboard/export?format=${format}${qs ? `&${qs}` : ""}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : "Export failed");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? `dashboard.${format}`;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

/** @deprecated use loadDashboardFilters */
export function getDashboardPeriodDays(): DashboardPeriodPreset {
  const f = loadDashboardFilters();
  if (f.periodMode === "custom") return 30;
  return Number(f.periodMode) as DashboardPeriodPreset;
}

/** @deprecated use saveDashboardFilters */
export function setDashboardPeriodDays(days: DashboardPeriodPreset): void {
  saveDashboardFilters({ ...loadDashboardFilters(), periodMode: String(days) as DashboardPeriodMode });
}

export const DASHBOARD_PERIOD_OPTIONS = DASHBOARD_PERIOD_PRESETS;
