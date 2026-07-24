import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatResearchFilters, researchProgressLabel, type ResearchProgress } from "../utils/researchFilters";

type ResearchDetail = {
  id: number;
  title: string;
  prompt: string;
  filters_json: Record<string, unknown>;
  status: string;
  call_count: number;
  call_ids: number[] | null;
  llm_model: string | null;
  report_markdown: string | null;
  error_message: string | null;
  user_name: string | null;
  created_at: string;
  finished_at: string | null;
};

const STATUS_LABEL: Record<string, string> = {
  pending: "В очереди",
  running: "Анализ",
  completed: "Готово",
  error: "Ошибка",
};

export default function ResearchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [progress, setProgress] = useState<ResearchProgress | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["research", id],
    queryFn: () => api.get<ResearchDetail>(`/research/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "pending" || status === "running") return 10000;
      return false;
    },
  });

  const isActive = data?.status === "pending" || data?.status === "running";

  useEffect(() => {
    if (!id || !isActive) return;
    const es = new EventSource(`/api/v1/research/${id}/events`, { withCredentials: true });
    const handle = (ev: MessageEvent) => {
      try {
        const payload = JSON.parse(ev.data) as ResearchProgress;
        setProgress(payload);
        if (payload.done) {
          qc.invalidateQueries({ queryKey: ["research", id] });
          qc.invalidateQueries({ queryKey: ["research"] });
        }
      } catch {
        /* ignore ping */
      }
    };
    es.addEventListener("status", handle as EventListener);
    es.onmessage = handle;
    return () => es.close();
  }, [id, isActive, qc]);

  useEffect(() => {
    if (data?.status === "completed" || data?.status === "error") {
      setProgress(null);
    }
  }, [data?.status]);

  if (isLoading || !data) {
    return <p className="empty">Загрузка...</p>;
  }

  const progressText =
    data.status === "error"
      ? data.error_message || "Ошибка анализа"
      : researchProgressLabel(progress);

  return (
    <>
      <Link to="/research" className="back-link">← К списку</Link>
      <h1 className="page-title">{data.title}</h1>
      <div className="btn-row" style={{ marginBottom: "var(--space-3)" }}>
        <p className="text-muted">
          {STATUS_LABEL[data.status] || data.status}
          {data.user_name ? ` · ${data.user_name}` : ""}
          {data.created_at ? ` · ${new Date(data.created_at).toLocaleString("ru")}` : ""}
        </p>
        {data.status === "completed" && data.report_markdown && (
          <>
            <a href={`/api/v1/research/${data.id}/export?format=md`} className="btn btn-secondary btn-sm" download>
              Скачать Markdown
            </a>
            <a href={`/api/v1/research/${data.id}/export?format=json`} className="btn btn-secondary btn-sm" download>
              Скачать JSON
            </a>
          </>
        )}
      </div>

      <div className="card" style={{ marginBottom: "var(--space-4)" }}>
        <h3>Параметры</h3>
        <p><strong>Фильтры:</strong> {formatResearchFilters(data.filters_json)}</p>
        <p><strong>Звонков в выборке:</strong> {data.call_count || "—"}</p>
        {data.llm_model && <p><strong>Модель:</strong> {data.llm_model}</p>}
        <details style={{ marginTop: "var(--space-3)" }}>
          <summary>Промпт</summary>
          <pre className="report-pre">{data.prompt}</pre>
        </details>
      </div>

      {isActive && (
        <div className="card" style={{ marginBottom: "var(--space-4)" }}>
          <p className="text-hint">{progressText}</p>
          {progress?.step === "map" && progress.batch != null && progress.batch_total != null && (
            <div className="progress">
              <div className="progress__track">
                <div
                  className="progress__fill"
                  style={{ width: `${Math.round((progress.batch / progress.batch_total) * 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {data.status === "error" && (
        <div className="card card--error" style={{ marginBottom: "var(--space-4)" }}>
          <p className="text-error">{data.error_message || "Ошибка анализа"}</p>
        </div>
      )}

      {data.status === "completed" && data.report_markdown && (
        <div className="card">
          <h3>Отчёт</h3>
          <pre className="report-pre report-body">{data.report_markdown}</pre>
        </div>
      )}
    </>
  );
}
