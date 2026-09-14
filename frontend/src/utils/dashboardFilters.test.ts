import { describe, expect, it } from "vitest";
import { buildDashboardQueryString, getDefaultDashboardFilters } from "./dashboardFilters";

describe("buildDashboardQueryString", () => {
  it("uses period_days for presets", () => {
    const qs = buildDashboardQueryString({ ...getDefaultDashboardFilters(), periodMode: "7" });
    expect(qs).toContain("period_days=7");
  });

  it("uses date range for custom mode", () => {
    const qs = buildDashboardQueryString({
      periodMode: "custom",
      dateFrom: "2026-01-01",
      dateTo: "2026-01-31",
      scenarioId: 3,
    });
    expect(qs).toContain("date_from=2026-01-01");
    expect(qs).toContain("date_to=2026-01-31");
    expect(qs).toContain("scenario_id=3");
  });
});
