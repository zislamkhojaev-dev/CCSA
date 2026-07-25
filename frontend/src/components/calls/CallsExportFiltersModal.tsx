import { useCallback, useEffect, useState } from "react";
import SearchableSelect from "../SearchableSelect";
import { fetchTagOptions } from "../TagMultiPicker.utils";
import type { CallExportFiltersPayload, CallExportFormat } from "../../utils/callsExport";

export type CallsFilterDraft = {
  statusFilter: string;
  operatorMatch: "eq" | "contains";
  operatorValue: string;
  clientMatch: "eq" | "contains";
  clientValue: string;
  dateFrom: string;
  dateTo: string;
  durationOp: "eq" | "lt" | "gt" | "";
  durationValue: string;
  scoreOp: "eq" | "lt" | "gt" | "";
  scoreValue: string;
  tagId: number | null;
};

type Props = {
  open: boolean;
  format: CallExportFormat;
  initial: CallsFilterDraft;
  busy?: boolean;
  statusText?: string | null;
  statusError?: boolean;
  onClose: () => void;
  onSubmit: (filters: CallExportFiltersPayload) => void;
};

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

export function draftToExportFilters(d: CallsFilterDraft): CallExportFiltersPayload {
  return {
    status_filter: d.statusFilter || null,
    operator_match: d.operatorValue.trim() ? d.operatorMatch : null,
    operator_value: d.operatorValue.trim() || null,
    client_match: d.clientValue.trim() ? d.clientMatch : null,
    client_value: d.clientValue.trim() || null,
    date_from: d.dateFrom || null,
    date_to: d.dateTo || null,
    duration_op: d.durationValue && d.durationOp ? d.durationOp : null,
    duration_value: d.durationValue ? Number(d.durationValue) : null,
    score_op: d.scoreValue && d.scoreOp ? d.scoreOp : null,
    score_value: d.scoreValue ? Number(d.scoreValue) : null,
    tag_id: d.tagId,
  };
}

export default function CallsExportFiltersModal({
  open,
  format,
  initial,
  busy,
  statusText,
  statusError,
  onClose,
  onSubmit,
}: Props) {
  const [draft, setDraft] = useState<CallsFilterDraft>(initial);
  const fetchTags = useCallback((q: string) => fetchTagOptions(q), []);

  useEffect(() => {
    if (open) setDraft(initial);
  }, [open, initial]);

  if (!open) return null;

  const set = <K extends keyof CallsFilterDraft>(key: K, value: CallsFilterDraft[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="dash-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="dash-modal calls-export-modal"
        role="dialog"
        aria-labelledby="calls-export-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="calls-export-modal-title" className="modal-title">
          Экспорт звонков ({format.toUpperCase()})
        </h2>
        <p className="form-hint mb-3">
          Укажите фильтры выборки. Файл будет собран в фоне и скачается автоматически.
        </p>

        <div className="calls-filters-grid">
          <div className="filter-field filter-field--span-2">
            <label htmlFor="exp-filter-operator">Оператор</label>
            <div className="filter-inline filter-inline--match">
              <select
                id="exp-filter-operator-match"
                aria-label="Условие оператора"
                value={draft.operatorMatch}
                onChange={(e) => set("operatorMatch", e.target.value as "eq" | "contains")}
                disabled={busy}
              >
                {MATCH_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <input
                id="exp-filter-operator"
                type="text"
                placeholder="Имя"
                value={draft.operatorValue}
                onChange={(e) => set("operatorValue", e.target.value)}
                disabled={busy}
              />
            </div>
          </div>

          <div className="filter-field filter-field--span-2">
            <label htmlFor="exp-filter-client">Клиент</label>
            <div className="filter-inline filter-inline--match">
              <select
                id="exp-filter-client-match"
                aria-label="Условие клиента"
                value={draft.clientMatch}
                onChange={(e) => set("clientMatch", e.target.value as "eq" | "contains")}
                disabled={busy}
              >
                {MATCH_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <input
                id="exp-filter-client"
                type="text"
                placeholder="Номер"
                value={draft.clientValue}
                onChange={(e) => set("clientValue", e.target.value)}
                disabled={busy}
              />
            </div>
          </div>

          <div className="filter-field">
            <label htmlFor="exp-filter-from">С</label>
            <input
              id="exp-filter-from"
              type="date"
              value={draft.dateFrom}
              onChange={(e) => set("dateFrom", e.target.value)}
              disabled={busy}
            />
          </div>
          <div className="filter-field">
            <label htmlFor="exp-filter-to">По</label>
            <input
              id="exp-filter-to"
              type="date"
              value={draft.dateTo}
              onChange={(e) => set("dateTo", e.target.value)}
              disabled={busy}
            />
          </div>

          <div className="filter-field">
            <label htmlFor="exp-filter-duration">Длит., с</label>
            <div className="filter-inline filter-inline--num">
              <select
                id="exp-filter-duration-op"
                aria-label="Условие длительности"
                value={draft.durationOp || "gt"}
                onChange={(e) => set("durationOp", e.target.value as CallsFilterDraft["durationOp"])}
                disabled={busy}
              >
                {NUM_OP_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <input
                id="exp-filter-duration"
                type="number"
                min={0}
                placeholder="сек"
                value={draft.durationValue}
                onChange={(e) => set("durationValue", e.target.value)}
                disabled={busy}
              />
            </div>
          </div>

          <div className="filter-field">
            <label htmlFor="exp-filter-score">Оценка</label>
            <div className="filter-inline filter-inline--num">
              <select
                id="exp-filter-score-op"
                aria-label="Условие оценки"
                value={draft.scoreOp || "eq"}
                onChange={(e) => set("scoreOp", e.target.value as CallsFilterDraft["scoreOp"])}
                disabled={busy}
              >
                {NUM_OP_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <input
                id="exp-filter-score"
                type="number"
                min={0}
                max={100}
                placeholder="%"
                value={draft.scoreValue}
                onChange={(e) => set("scoreValue", e.target.value)}
                disabled={busy}
              />
            </div>
          </div>

          <div className="filter-field filter-field--span-2">
            <label htmlFor="exp-filter-status">Статус</label>
            <select
              id="exp-filter-status"
              value={draft.statusFilter}
              onChange={(e) => set("statusFilter", e.target.value)}
              disabled={busy}
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value || "all"} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-field filter-field--span-2">
            <label htmlFor="exp-filter-tag">Тег</label>
            <SearchableSelect
              id="exp-filter-tag"
              value={draft.tagId}
              onChange={(id) => set("tagId", id)}
              emptyLabel="Все теги"
              placeholder="Поиск тега…"
              fetchOptions={fetchTags}
            />
          </div>
        </div>

        {statusText && (
          <p
            className={`form-hint mt-3 ${statusError ? "text-error" : ""}`}
            role="status"
            aria-live="polite"
          >
            {statusText}
          </p>
        )}

        <div className="btn-row mt-4" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => onSubmit(draftToExportFilters(draft))}
          >
            {busy ? "Экспорт…" : "Экспорт"}
          </button>
        </div>
      </div>
    </div>
  );
}
