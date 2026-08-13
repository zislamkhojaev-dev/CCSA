import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { api } from "../api/client";
import SearchableSelect from "../components/SearchableSelect";
import { fetchTagOptions } from "../components/TagMultiPicker.utils";
import ScoreBadge from "../components/ScoreBadge";
import DashboardExportMenu from "../components/dashboard/DashboardExportMenu";
import CallsExportFiltersModal, {
  type CallsFilterDraft,
} from "../components/calls/CallsExportFiltersModal";
import { callStatusLabel } from "../utils/callStatus";
import {
  downloadCallsExportJob,
  downloadSelectedCallsExport,
  startCallsExportJob,
  waitForCallsExportJob,
  type CallExportFiltersPayload,
  type CallExportFormat,
} from "../utils/callsExport";

type CallItem = {
  id: number;
  call_uuid: string;
  operator_name: string | null;
  direction: string | null;
  duration: number | null;
  client_number: string | null;
  call_timestamp: string | null;
  status: string;
  total_score: number | null;
};

type Paginated = { items: CallItem[]; total: number; page: number; page_size: number };

type TextMatch = "" | "eq" | "contains";
type NumOp = "" | "eq" | "lt" | "gt";
type SortKey = "id" | "operator_name" | "client_number" | "call_timestamp" | "duration" | "status" | "total_score";
type SortDir = "asc" | "desc";

const STATUS_OPTIONS = [
  { value: "", label: "Все статусы" },
  { value: "pending", label: "В очереди" },
  { value: "transcribing", label: "Распознавание" },
  { value: "transcribed", label: "Транскрибирован" },
  { value: "analyzing", label: "Анализ" },
  { value: "analyzed", label: "Готово" },
  { value: "error", label: "Ошибка" },
];

const MATCH_OPTIONS = [
  { value: "contains", label: "содержит" },
  { value: "eq", label: "равно" },
];

const NUM_OP_OPTIONS = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "gt", label: ">" },
];

const SORTABLE: { key: SortKey; label: string }[] = [
  { key: "id", label: "ID" },
  { key: "operator_name", label: "Оператор" },
  { key: "client_number", label: "Клиент" },
  { key: "call_timestamp", label: "Дата" },
  { key: "duration", label: "Длительность" },
  { key: "status", label: "Статус" },
  { key: "total_score", label: "Оценка" },
];

function formatDuration(sec: number | null): string {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}м ${s}с` : `${s}с`;
}

function buildQueryParams(
  page: number,
  pageSize: number,
  filters: {
    statusFilter: string;
    operatorMatch: TextMatch;
    operatorValue: string;
    clientMatch: TextMatch;
    clientValue: string;
    dateFrom: string;
    dateTo: string;
    durationOp: NumOp;
    durationValue: string;
    scoreOp: NumOp;
    scoreValue: string;
    tagId: number | null;
    sortBy: SortKey;
    sortDir: SortDir;
  },
): URLSearchParams {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort_by: filters.sortBy,
    sort_order: filters.sortDir,
  });
  if (filters.statusFilter) params.set("status_filter", filters.statusFilter);
  if (filters.operatorValue.trim() && filters.operatorMatch) {
    params.set("operator_match", filters.operatorMatch);
    params.set("operator_value", filters.operatorValue.trim());
  }
  if (filters.clientValue.trim() && filters.clientMatch) {
    params.set("client_match", filters.clientMatch);
    params.set("client_value", filters.clientValue.trim());
  }
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.durationValue && filters.durationOp) {
    params.set("duration_op", filters.durationOp);
    params.set("duration_value", filters.durationValue);
  }
  if (filters.scoreValue && filters.scoreOp) {
    params.set("score_op", filters.scoreOp);
    params.set("score_value", filters.scoreValue);
  }
  if (filters.tagId != null) params.set("tag_id", String(filters.tagId));
  return params;
}

const FILTERS_OPEN_KEY = "ccsa-calls-filters-open";

function readFiltersOpenDefault(): boolean {
  try {
    return sessionStorage.getItem(FILTERS_OPEN_KEY) !== "0";
  } catch {
    return true;
  }
}

function countActiveCallFilters(f: {
  statusFilter: string;
  operatorValue: string;
  clientValue: string;
  dateFrom: string;
  dateTo: string;
  durationValue: string;
  scoreValue: string;
  tagId: number | null;
}): number {
  let n = 0;
  if (f.statusFilter) n++;
  if (f.operatorValue.trim()) n++;
  if (f.clientValue.trim()) n++;
  if (f.dateFrom) n++;
  if (f.dateTo) n++;
  if (f.durationValue) n++;
  if (f.scoreValue) n++;
  if (f.tagId != null) n++;
  return n;
}

function useDebouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export default function CallsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const [statusFilter, setStatusFilter] = useState("");
  const [operatorMatch, setOperatorMatch] = useState<TextMatch>("contains");
  const [operatorValue, setOperatorValue] = useState("");
  const [clientMatch, setClientMatch] = useState<TextMatch>("contains");
  const [clientValue, setClientValue] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [durationOp, setDurationOp] = useState<NumOp>("gt");
  const [durationValue, setDurationValue] = useState("");
  const [scoreOp, setScoreOp] = useState<NumOp>("eq");
  const [scoreValue, setScoreValue] = useState("");
  const [tagId, setTagId] = useState<number | null>(null);
  const [sortBy, setSortBy] = useState<SortKey>("call_timestamp");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [filtersOpen, setFiltersOpen] = useState(readFiltersOpenDefault);
  const debouncedOperatorValue = useDebouncedValue(operatorValue, 400);
  const debouncedClientValue = useDebouncedValue(clientValue, 400);

  useEffect(() => {
    setPage(1);
  }, [debouncedOperatorValue, debouncedClientValue]);

  const activeFilterCount = useMemo(
    () =>
      countActiveCallFilters({
        statusFilter,
        operatorValue,
        clientValue,
        dateFrom,
        dateTo,
        durationValue,
        scoreValue,
        tagId,
      }),
    [statusFilter, operatorValue, clientValue, dateFrom, dateTo, durationValue, scoreValue, tagId],
  );

  const toggleFiltersOpen = () => {
    setFiltersOpen((open) => {
      const next = !open;
      try {
        sessionStorage.setItem(FILTERS_OPEN_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  const filterState = useMemo(
    () => ({
      statusFilter,
      operatorMatch,
      operatorValue: debouncedOperatorValue,
      clientMatch,
      clientValue: debouncedClientValue,
      dateFrom,
      dateTo,
      durationOp,
      durationValue,
      scoreOp,
      scoreValue,
      tagId,
      sortBy,
      sortDir,
    }),
    [
      statusFilter,
      operatorMatch,
      debouncedOperatorValue,
      clientMatch,
      debouncedClientValue,
      dateFrom,
      dateTo,
      durationOp,
      durationValue,
      scoreOp,
      scoreValue,
      tagId,
      sortBy,
      sortDir,
    ],
  );

  const queryKey = ["calls", page, pageSize, filterState];

  const { data, isLoading, isFetching } = useQuery({
    queryKey,
    queryFn: () => api.get<Paginated>(`/calls?${buildQueryParams(page, pageSize, filterState)}`),
    placeholderData: keepPreviousData,
  });

  const deleteMutation = useMutation({
    mutationFn: (ids: number[]) => api.post<{ message: string }>("/calls/bulk-delete", { ids }),
    onSuccess: () => {
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ["calls"] });
    },
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;
  const pageIds = data?.items.map((c) => c.id) ?? [];
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  const toggleSort = (col: SortKey) => {
    if (sortBy === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(col);
      setSortDir(col === "call_timestamp" || col === "id" ? "desc" : "asc");
    }
    setPage(1);
  };

  const toggleRow = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllOnPage = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) {
        pageIds.forEach((id) => next.delete(id));
      } else {
        pageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const fetchTags = useCallback((q: string) => fetchTagOptions(q), []);

  const resetFilters = () => {
    setStatusFilter("");
    setOperatorMatch("contains");
    setOperatorValue("");
    setClientMatch("contains");
    setClientValue("");
    setDateFrom("");
    setDateTo("");
    setDurationOp("gt");
    setDurationValue("");
    setScoreOp("eq");
    setScoreValue("");
    setTagId(null);
    setPage(1);
  };

  const handleDelete = () => {
    if (!selected.size) return;
    if (!window.confirm(`Удалить выбранные звонки (${selected.size})? Это действие необратимо.`)) return;
    deleteMutation.mutate([...selected]);
  };

  const [exporting, setExporting] = useState(false);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState<CallExportFormat>("csv");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportStatus, setExportStatus] = useState<{ text: string; error: boolean } | null>(null);

  const exportFilterDraft: CallsFilterDraft = useMemo(
    () => ({
      statusFilter,
      operatorMatch: operatorMatch || "contains",
      operatorValue,
      clientMatch: clientMatch || "contains",
      clientValue,
      dateFrom,
      dateTo,
      durationOp: durationOp || "gt",
      durationValue,
      scoreOp: scoreOp || "eq",
      scoreValue,
      tagId,
    }),
    [
      statusFilter,
      operatorMatch,
      operatorValue,
      clientMatch,
      clientValue,
      dateFrom,
      dateTo,
      durationOp,
      durationValue,
      scoreOp,
      scoreValue,
      tagId,
    ],
  );

  const handleExportPick = async (format: CallExportFormat) => {
    if (selected.size > 0) {
      setExporting(true);
      try {
        await downloadSelectedCallsExport([...selected], format);
      } catch (e: unknown) {
        alert(e instanceof Error ? e.message : "Ошибка экспорта");
      } finally {
        setExporting(false);
      }
      return;
    }
    setExportFormat(format);
    setExportStatus(null);
    setExportModalOpen(true);
  };

  const handleExportJobSubmit = async (filters: CallExportFiltersPayload) => {
    setExportBusy(true);
    setExportStatus({ text: "Задача на экспорт создана…", error: false });
    try {
      const job = await startCallsExportJob(exportFormat, filters);
      setExportStatus({
        text: job.message || "Задача на экспорт создана. Ожидаем файл…",
        error: false,
      });
      const result = await waitForCallsExportJob(job.id);
      if (result.status === "error") {
        setExportStatus({ text: result.error || "Ошибка экспорта", error: true });
        return;
      }
      setExportStatus({ text: "Готово, скачиваем файл…", error: false });
      await downloadCallsExportJob(job.id, exportFormat);
      setExportStatus({
        text: `Скачано звонков: ${result.row_count ?? "—"}`,
        error: false,
      });
    } catch (e: unknown) {
      setExportStatus({
        text: e instanceof Error ? e.message : "Ошибка экспорта",
        error: true,
      });
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Звонки</h1>
        <div className="dash-toolbar-actions">
          <DashboardExportMenu onExport={handleExportPick} exporting={exporting || exportBusy} />
          {selected.size > 0 && (
            <button
              type="button"
              className="btn btn-danger"
              disabled={deleteMutation.isPending}
              onClick={handleDelete}
            >
              {deleteMutation.isPending ? "Удаление…" : `Удалить (${selected.size})`}
            </button>
          )}
        </div>
      </div>

      <CallsExportFiltersModal
        open={exportModalOpen}
        format={exportFormat}
        initial={exportFilterDraft}
        busy={exportBusy}
        statusText={exportStatus?.text ?? null}
        statusError={exportStatus?.error}
        onClose={() => {
          if (!exportBusy) {
            setExportModalOpen(false);
            setExportStatus(null);
          }
        }}
        onSubmit={handleExportJobSubmit}
      />

      <div className={`card calls-filters${filtersOpen ? " calls-filters--open" : ""}`}>
        <div className="calls-filters-header">
          <button
            type="button"
            className="calls-filters-toggle"
            onClick={toggleFiltersOpen}
            aria-expanded={filtersOpen}
          >
            {filtersOpen ? <ChevronUp size={18} aria-hidden /> : <ChevronDown size={18} aria-hidden />}
            <span>Фильтры</span>
            {activeFilterCount > 0 && (
              <span className="calls-filters-badge">{activeFilterCount}</span>
            )}
          </button>
          <div className="calls-filters-header-actions">
            {isFetching && !isLoading && <span className="calls-fetching">Обновление…</span>}
            {activeFilterCount > 0 && (
              <button type="button" className="calls-filters-reset" onClick={resetFilters}>
                Сбросить
              </button>
            )}
          </div>
        </div>

        {filtersOpen && (
          <div className="calls-filters-body">
            <div className="calls-filters-grid">
              <div className="filter-field filter-field--span-2">
                <label htmlFor="calls-filter-operator">Оператор</label>
                <div className="filter-inline filter-inline--match">
                  <select
                    id="calls-filter-operator-match"
                    aria-label="Условие оператора"
                    value={operatorMatch}
                    onChange={(e) => { setOperatorMatch(e.target.value as TextMatch); setPage(1); }}
                  >
                    {MATCH_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <input
                    id="calls-filter-operator"
                    type="text"
                    placeholder="Имя"
                    value={operatorValue}
                    onChange={(e) => { setOperatorValue(e.target.value); setPage(1); }}
                  />
                </div>
              </div>
              <div className="filter-field filter-field--span-2">
                <label htmlFor="calls-filter-client">Клиент</label>
                <div className="filter-inline filter-inline--match">
                  <select
                    id="calls-filter-client-match"
                    aria-label="Условие клиента"
                    value={clientMatch}
                    onChange={(e) => { setClientMatch(e.target.value as TextMatch); setPage(1); }}
                  >
                    {MATCH_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <input
                    id="calls-filter-client"
                    type="text"
                    placeholder="Номер"
                    value={clientValue}
                    onChange={(e) => { setClientValue(e.target.value); setPage(1); }}
                  />
                </div>
              </div>

              <div className="filter-field">
                <label htmlFor="calls-filter-date-from">С</label>
                <input
                  id="calls-filter-date-from"
                  type="date"
                  value={dateFrom}
                  onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
                />
              </div>
              <div className="filter-field">
                <label htmlFor="calls-filter-date-to">По</label>
                <input
                  id="calls-filter-date-to"
                  type="date"
                  value={dateTo}
                  onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
                />
              </div>
              <div className="filter-field">
                <label htmlFor="calls-filter-duration">Длит., с</label>
                <div className="filter-inline filter-inline--num">
                  <select
                    id="calls-filter-duration-op"
                    aria-label="Условие длительности"
                    value={durationOp}
                    onChange={(e) => { setDurationOp(e.target.value as NumOp); setPage(1); }}
                  >
                    {NUM_OP_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <input
                    id="calls-filter-duration"
                    type="number"
                    min={0}
                    placeholder="сек"
                    value={durationValue}
                    onChange={(e) => { setDurationValue(e.target.value); setPage(1); }}
                  />
                </div>
              </div>
              <div className="filter-field">
                <label htmlFor="calls-filter-score">Оценка</label>
                <div className="filter-inline filter-inline--num">
                  <select
                    id="calls-filter-score-op"
                    aria-label="Условие оценки"
                    value={scoreOp}
                    onChange={(e) => { setScoreOp(e.target.value as NumOp); setPage(1); }}
                  >
                    {NUM_OP_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <input
                    id="calls-filter-score"
                    type="number"
                    min={0}
                    max={100}
                    placeholder="%"
                    value={scoreValue}
                    onChange={(e) => { setScoreValue(e.target.value); setPage(1); }}
                  />
                </div>
              </div>

              <div className="filter-field filter-field--span-2">
                <label htmlFor="calls-filter-status">Статус</label>
                <select
                  id="calls-filter-status"
                  value={statusFilter}
                  onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
                >
                  {STATUS_OPTIONS.map((o) => (
                    <option key={o.value || "all"} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div className="filter-field filter-field--span-2">
                <label htmlFor="calls-filter-tag">Тег</label>
                <SearchableSelect
                  id="calls-filter-tag"
                  value={tagId}
                  onChange={(id) => { setTagId(id); setPage(1); }}
                  emptyLabel="Все теги"
                  placeholder="Поиск тега…"
                  fetchOptions={fetchTags}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="card table-wrap">
        {isLoading ? (
          <p className="empty">Загрузка...</p>
        ) : (
          <table className="calls-table">
            <thead>
              <tr>
                <th className="col-check">
                  <input
                    type="checkbox"
                    checked={allOnPageSelected}
                    onChange={toggleAllOnPage}
                    aria-label="Выбрать все на странице"
                  />
                </th>
                {SORTABLE.map((col) => (
                  <th key={col.key}>
                    <button
                      type="button"
                      className={`th-sort${sortBy === col.key ? " th-sort-active" : ""}`}
                      onClick={() => toggleSort(col.key)}
                    >
                      {col.label}
                      {sortBy === col.key && (
                        <span className="sort-arrow" aria-hidden>{sortDir === "asc" ? " ↑" : " ↓"}</span>
                      )}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={8} className="empty">
                    Звонки не найдены
                  </td>
                </tr>
              )}
              {data?.items.map((c) => (
                <tr key={c.id} className={selected.has(c.id) ? "row-selected" : undefined}>
                  <td className="col-check">
                    <input
                      type="checkbox"
                      checked={selected.has(c.id)}
                      onChange={() => toggleRow(c.id)}
                      aria-label={`Выбрать звонок ${c.id}`}
                    />
                  </td>
                  <td>
                    <Link to={`/calls/${c.id}`}>#{c.id}</Link>
                  </td>
                  <td>{c.operator_name || "—"}</td>
                  <td>{c.client_number || "—"}</td>
                  <td>{c.call_timestamp ? new Date(c.call_timestamp).toLocaleString("ru") : "—"}</td>
                  <td>{formatDuration(c.duration)}</td>
                  <td>
                    <span className="badge badge-gray" title={c.status}>
                      {callStatusLabel(c.status)}
                    </span>
                  </td>
                  <td>
                    <ScoreBadge score={c.total_score} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="pagination">
          <button type="button" className="btn btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Назад
          </button>
          <span>
            Стр. {page} / {totalPages} (всего {data?.total ?? 0})
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Вперёд
          </button>
          <label className="pagination-page-size">
            <span className="pagination-page-size-label">На странице</span>
            <select
              className="form-input"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              aria-label="Количество на странице"
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </label>
        </div>
      </div>
    </>
  );
}
