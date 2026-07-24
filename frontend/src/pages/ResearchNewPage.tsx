import { useCallback, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import SearchableSelect from "../components/SearchableSelect";
import { fetchTagOptions } from "../components/TagMultiPicker.utils";

type Operator = { id: number; full_name: string };
type PaginatedOps = { items: Operator[]; total: number };
type TagOption = { id: number; name: string };
type FilterOptions = { queues: string[]; tags: TagOption[] };

type Preview = { count: number; max_calls: number };

type NumOp = "" | "eq" | "lt" | "gt";

export default function ResearchNewPage() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [direction, setDirection] = useState("");
  const [operatorId, setOperatorId] = useState<number | "">("");
  const [queue, setQueue] = useState("");
  const [tagId, setTagId] = useState<number | null>(null);
  const [scoreOp, setScoreOp] = useState<NumOp>("");
  const [scoreValue, setScoreValue] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [busy, setBusy] = useState(false);

  const { data: operators } = useQuery({
    queryKey: ["operators-research"],
    queryFn: () => api.get<PaginatedOps>("/operators?page=1&page_size=100"),
  });

  const { data: filterOptions } = useQuery({
    queryKey: ["research-filter-options"],
    queryFn: () => api.get<FilterOptions>("/research/filter-options"),
  });

  const filters = () => ({
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    direction: direction || undefined,
    operator_id: operatorId === "" ? undefined : operatorId,
    queue: queue || undefined,
    tag_id: tagId ?? undefined,
    score_op: scoreOp || undefined,
    score_value: scoreValue && scoreOp ? Number(scoreValue) : undefined,
  });

  const fetchTags = useCallback((q: string) => fetchTagOptions(q), []);

  const checkPreview = async () => {
    setPreviewError("");
    setPreview(null);
    try {
      const r = await api.post<Preview>("/research/preview", { filters: filters() });
      setPreview(r);
    } catch (e: unknown) {
      setPreviewError(e instanceof Error ? e.message : "Ошибка проверки выборки");
    }
  };

  const submit = async () => {
    setSubmitError("");
    if (!title.trim() || !prompt.trim()) {
      setSubmitError("Укажите название и промпт");
      return;
    }
    if (preview && preview.count === 0) {
      setSubmitError("Нет звонков для анализа. Проверьте фильтры и нажмите «Проверить выборку».");
      return;
    }
    setBusy(true);
    try {
      const r = await api.post<{ id: number }>("/research", {
        title: title.trim(),
        prompt: prompt.trim(),
        filters: filters(),
      });
      navigate(`/research/${r.id}`);
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "detail" in e
          ? String((e as { detail: string }).detail)
          : e instanceof Error
            ? e.message
            : "Не удалось запустить исследование";
      setSubmitError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Link to="/research" className="back-link">← К списку</Link>
      <h1 className="page-title">Новое исследование</h1>

      <div className="card card--narrow">
        <label className="form-label">
          Название
          <input
            className="form-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Например: Жалобы на Paynet за март"
          />
        </label>

        <label className="form-label" style={{ marginTop: "var(--space-4)" }}>
          Промпт для LLM
          <textarea
            className="form-input"
            rows={8}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Какие основные причины недовольства клиентов? Какие темы повторяются чаще всего?"
          />
        </label>

        <h3 className="form-section-title">Фильтры звонков</h3>
        <div className="filter-grid">
          <label className="form-label">
            Дата от
            <input type="date" className="form-input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="form-label">
            Дата до
            <input type="date" className="form-input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <label className="form-label">
            Направление
            <select className="form-input" value={direction} onChange={(e) => setDirection(e.target.value)}>
              <option value="">Все</option>
              <option value="inbound">Входящий</option>
              <option value="outbound">Исходящий</option>
            </select>
          </label>
          <label className="form-label">
            Оператор
            <select
              className="form-input"
              value={operatorId === "" ? "" : String(operatorId)}
              onChange={(e) => setOperatorId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">Все</option>
              {operators?.items.map((op) => (
                <option key={op.id} value={op.id}>{op.full_name}</option>
              ))}
            </select>
          </label>
          <label className="form-label">
            Очередь
            <select className="form-input" value={queue} onChange={(e) => setQueue(e.target.value)}>
              <option value="">Все</option>
              {filterOptions?.queues.map((q) => (
                <option key={q} value={q}>{q}</option>
              ))}
            </select>
          </label>
          <label className="form-label">
            Тег
            <SearchableSelect
              value={tagId}
              onChange={setTagId}
              emptyLabel="Все теги"
              placeholder="Поиск тега…"
              fetchOptions={fetchTags}
            />
          </label>
          <label className="form-label">
            Оценка
            <div className="filter-inline">
              <select className="form-input" value={scoreOp} onChange={(e) => setScoreOp(e.target.value as NumOp)}>
                <option value="">—</option>
                <option value="eq">=</option>
                <option value="lt">&lt;</option>
                <option value="gt">&gt;</option>
              </select>
              <input
                className="form-input"
                type="number"
                min={0}
                max={100}
                placeholder="%"
                value={scoreValue}
                onChange={(e) => setScoreValue(e.target.value)}
              />
            </div>
          </label>
        </div>

        <div className="btn-row" style={{ marginTop: "var(--space-5)" }}>
          <button type="button" className="btn btn-secondary" onClick={checkPreview}>
            Проверить выборку
          </button>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "Запуск..." : "Запустить анализ"}
          </button>
        </div>

        {preview && (
          <p className="text-hint" style={{ marginTop: "var(--space-4)" }}>
            Найдено звонков с транскриптом: <strong>{preview.count}</strong> (макс. {preview.max_calls})
          </p>
        )}
        {previewError && <p className="text-error">{previewError}</p>}
        {submitError && <p className="text-error">{submitError}</p>}
      </div>
    </>
  );
}
