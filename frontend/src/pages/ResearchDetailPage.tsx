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
      <div style={{ marginBottom: "1rem" }}>
        <Link to="/research">← К списку</Link>
      </div>
      <h1 className="page-title">{data.title}</h1>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", marginBottom: "0.35rem" }}>
        <p className="text-muted" style={{ margin: 0 }}>
          {STATUS_LABEL[data.status] || data.status}
          {data.user_name ? ` · ${data.user_name}` : ""}
          {data.created_at ? ` · ${new Date(data.created_at).toLocaleString("ru")}` : ""}
        </p>
        {data.status === "completed" && data.report_markdown && (
          <>
            <a
              href={`/api/v1/research/${data.id}/export?format=md`}
              className="btn btn-secondary"
              download
              style={{ padding: "0.35rem 0.75rem", fontSize: "0.8125rem" }}
            >
              Скачать Markdown
            </a>
            <a
              href={`/api/v1/research/${data.id}/export?format=json`}
              className="btn btn-secondary"
              download
              style={{ padding: "0.35rem 0.75rem", fontSize: "0.8125rem" }}
            >
              Скачать JSON
            </a>
          </>
        )}
      </div>

      <div className="card" style={{ padding: "1.25rem", marginBottom: "1rem" }}>
        <h3>Параметры</h3>
        <p>
          <strong>Фильтры:</strong> {formatResearchFilters(data.filters_json)}
        </p>
        <p>
          <strong>Звонков в выборке:</strong> {data.call_count || "—"}
        </p>
        {data.llm_model && (
          <p>
            <strong>Модель:</strong> {data.llm_model}
          </p>
        )}
        <details style={{ marginTop: "0.75rem" }}>
          <summary>Промпт</summary>
          <pre style={{ whiteSpace: "pre-wrap", marginTop: "0.5rem" }}>{data.prompt}</pre>
        </details>
      </div>

      {isActive && (
        <div className="card" style={{ padding: "1.25rem" }}>
          <p style={{ marginBottom: "0.75rem" }}>{progressText}</p>
          {progress?.step === "map" && progress.batch != null && progress.batch_total != null && (
            <div style={{ height: 8, background: "var(--md-surface-container-high)", borderRadius: 4, overflow: "hidden" }}>
              <div
                style={{
                  width: `${Math.round((progress.batch / progress.batch_total) * 100)}%`,
                  height: "100%",
                  background: "var(--md-primary)",
                  transition: "width 0.3s",
                }}
              />
            </div>
          )}
        </div>
      )}

      {data.status === "error" && (
        <div className="card" style={{ padding: "1.25rem", borderColor: "var(--danger)" }}>
          <p className="text-danger">{data.error_message || "Ошибка анализа"}</p>
        </div>
      )}

      {data.status === "completed" && data.report_markdown && (
        <div className="card" style={{ padding: "1.25rem" }}>
          <h3>Отчёт</h3>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              fontFamily: "inherit",
              lineHeight: 1.6,
              marginTop: "0.75rem",
            }}
          >
            {data.report_markdown}
          </pre>
        </div>
      )}
    </>
  );
}
