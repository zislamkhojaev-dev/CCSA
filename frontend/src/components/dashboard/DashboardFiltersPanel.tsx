import { ChevronDown, ChevronUp, Download } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { DashboardFiltersState, DashboardPeriodMode } from "../../utils/dashboardFilters";
import { DASHBOARD_PERIOD_PRESETS } from "../../utils/dashboardFilters";

type Props = {
  filters: DashboardFiltersState;
  onChange: (filters: DashboardFiltersState) => void;
  onExport: (format: "json" | "csv") => void;
  exporting?: boolean;
};

export default function DashboardFiltersPanel({ filters, onChange, onExport, exporting }: Props) {
  const [open, setOpen] = useState(true);
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios-list"],
    queryFn: () => api.get<{ id: number; name: string }[]>("/scenarios"),
    staleTime: 5 * 60 * 1000,
  });

  const set = (patch: Partial<DashboardFiltersState>) => onChange({ ...filters, ...patch });

  const activeCount =
    (filters.periodMode === "custom" && (filters.dateFrom || filters.dateTo) ? 1 : 0) +
    (filters.scenarioId ? 1 : 0);

  return (
    <div className={`card dash-filters${open ? " dash-filters--open" : ""}`}>
      <div className="dash-filters-header">
        <button
          type="button"
          className="dash-filters-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? <ChevronUp size={18} aria-hidden /> : <ChevronDown size={18} aria-hidden />}
          <span>Фильтры дашборда</span>
          {activeCount > 0 && <span className="dash-filters-badge">{activeCount}</span>}
        </button>
        <div className="dash-filters-header-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={exporting}
            onClick={() => onExport("csv")}
          >
            <Download size={14} />
            CSV
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={exporting}
            onClick={() => onExport("json")}
          >
            <Download size={14} />
            JSON
          </button>
        </div>
      </div>

      {open && (
        <div className="dash-filters-body">
          <div className="dash-filters-row">
            <div className="filter-field dash-filter-period">
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
              {filters.periodMode === "custom" && (
                <div className="dash-filter-period-dates">
                  <input
                    id="dash-filter-from"
                    type="date"
                    className="form-input dash-filter-control"
                    value={filters.dateFrom}
                    onChange={(e) => set({ dateFrom: e.target.value })}
                    aria-label="Дата с"
                  />
                  <input
                    id="dash-filter-to"
                    type="date"
                    className="form-input dash-filter-control"
                    value={filters.dateTo}
                    onChange={(e) => set({ dateTo: e.target.value })}
                    aria-label="Дата по"
                  />
                </div>
              )}
            </div>

            <div className="filter-field">
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
      )}
    </div>
  );
}
