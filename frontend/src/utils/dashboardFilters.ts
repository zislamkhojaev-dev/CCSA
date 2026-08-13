const STORAGE_KEY = "ccsa-dashboard-filters";

export const DASHBOARD_PERIOD_PRESETS = [7, 30, 90] as const;
export type DashboardPeriodPreset = (typeof DASHBOARD_PERIOD_PRESETS)[number];
export type DashboardPeriodMode = `${DashboardPeriodPreset}` | "custom";

export interface DashboardFiltersState {
  periodMode: DashboardPeriodMode;
  dateFrom: string;
  dateTo: string;
  scenarioId: number | null;
}

const DEFAULT_FILTERS: DashboardFiltersState = {
  periodMode: "30",
  dateFrom: "",
  dateTo: "",
  scenarioId: null,
};

export function getDefaultDashboardFilters(): DashboardFiltersState {
  return { ...DEFAULT_FILTERS };
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
    return {
      periodMode: validMode,
      dateFrom: typeof data.dateFrom === "string" ? data.dateFrom : "",
      dateTo: typeof data.dateTo === "string" ? data.dateTo : "",
      scenarioId: typeof data.scenarioId === "number" ? data.scenarioId : null,
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
  return [filters.periodMode, filters.dateFrom, filters.dateTo, filters.scenarioId ?? ""];
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
  if (filters.scenarioId) params.set("scenario_id", String(filters.scenarioId));
  return params.toString();
}

export function buildDashboardBatchBody(metrics: string[], filters: DashboardFiltersState) {
  const body: {
    metrics: string[];
    period_days: number;
    date_from?: string;
    date_to?: string;
    scenario_id?: number;
  } = {
    metrics,
    period_days: filters.periodMode === "custom" ? 30 : Number(filters.periodMode) || 30,
  };
  if (filters.periodMode === "custom") {
    if (filters.dateFrom) body.date_from = filters.dateFrom;
    if (filters.dateTo) body.date_to = filters.dateTo;
  }
  if (filters.scenarioId) body.scenario_id = filters.scenarioId;
  return body;
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
