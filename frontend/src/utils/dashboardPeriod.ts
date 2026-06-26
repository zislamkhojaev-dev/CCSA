const STORAGE_KEY = "ccsa-dashboard-period-days";

export const DASHBOARD_PERIOD_OPTIONS = [7, 30, 90] as const;
export type DashboardPeriodDays = (typeof DASHBOARD_PERIOD_OPTIONS)[number];

const DEFAULT_PERIOD: DashboardPeriodDays = 30;

export function getDashboardPeriodDays(): DashboardPeriodDays {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const n = raw ? Number(raw) : DEFAULT_PERIOD;
    if (DASHBOARD_PERIOD_OPTIONS.includes(n as DashboardPeriodDays)) {
      return n as DashboardPeriodDays;
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_PERIOD;
}

export function setDashboardPeriodDays(days: DashboardPeriodDays): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(days));
  } catch {
    /* ignore */
  }
}
