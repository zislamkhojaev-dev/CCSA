import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { DashboardFiltersState, DashboardPeriodMode } from "../../utils/dashboardFilters";
import { DASHBOARD_PERIOD_PRESETS } from "../../utils/dashboardFilters";

type Props = {
  filters: DashboardFiltersState;
  onChange: (filters: DashboardFiltersState) => void;
};

export default function DashboardFiltersPanel({ filters, onChange }: Props) {
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios-list"],
    queryFn: () => api.get<{ id: number; name: string }[]>("/scenarios"),
    staleTime: 5 * 60 * 1000,
  });

  const set = (patch: Partial<DashboardFiltersState>) => onChange({ ...filters, ...patch });

  return (
    <div className="card dash-filters">
      <div className="dash-filters-bar">
        <div className="dash-filters-period-group">
          <div className="filter-field">
            <label htmlFor="dash-filter-period">Период</label>
            <select
              id="dash-filter-period"
              className="form-input dash-filter-control"
              value={filters.periodMode}
              onChange={(e) => set({ periodMode: e.target.value as DashboardPeriodMode })}
            >
              {DASHBOARD_PERIOD_PRESETS.map((d) => (
                <option key={d} value={String(d)}>
                  {d} дней
                </option>
              ))}
              <option value="custom">Свой период</option>
            </select>
          </div>
          {filters.periodMode === "custom" && (
            <>
              <div className="filter-field dash-filter-date">
                <label htmlFor="dash-filter-from">С</label>
                <input
                  id="dash-filter-from"
                  type="date"
                  className="form-input dash-filter-control"
                  value={filters.dateFrom}
                  onChange={(e) => set({ dateFrom: e.target.value })}
                />
              </div>
              <div className="filter-field dash-filter-date">
                <label htmlFor="dash-filter-to">По</label>
                <input
                  id="dash-filter-to"
                  type="date"
                  className="form-input dash-filter-control"
                  value={filters.dateTo}
                  onChange={(e) => set({ dateTo: e.target.value })}
                />
              </div>
            </>
          )}
        </div>

        <div className="filter-field dash-filter-scenario">
          <label htmlFor="dash-filter-scenario">Сценарий</label>
          <select
            id="dash-filter-scenario"
            className="form-input dash-filter-control"
            value={filters.scenarioId ?? ""}
            onChange={(e) => set({ scenarioId: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">Все сценарии</option>
            {scenarios?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
