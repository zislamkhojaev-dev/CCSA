import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Plus, Trash2 } from "lucide-react";
import { api } from "../api/client";
import { formatResearchFilters } from "../utils/researchFilters";

type ResearchItem = {
  id: number;
  title: string;
  status: string;
  call_count: number;
  filters_json: Record<string, unknown>;
  user_name: string | null;
  created_at: string;
  finished_at: string | null;
};

type Paginated = { items: ResearchItem[]; total: number; page: number; page_size: number };

const STATUS_LABEL: Record<string, string> = {
  pending: "В очереди",
  running: "Анализ",
  completed: "Готово",
  error: "Ошибка",
};

function statusClass(status: string): string {
  if (status === "completed") return "badge-green";
  if (status === "error") return "badge-red";
  if (status === "running") return "badge-yellow";
  return "badge-gray";
}

function formatFilters(f: Record<string, unknown>): string {
  return formatResearchFilters(f);
}

export default function ResearchListPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["research"],
    queryFn: () => api.get<Paginated>("/research?page=1&page_size=50"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/research/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["research"] }),
  });

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Исследования</h1>
        <Link to="/research/new" className="btn btn-primary">
          <Plus size={16} /> Новое исследование
        </Link>
      </div>
      <p className="text-muted" style={{ marginBottom: "var(--space-4)" }}>
        LLM-метаанализ по транскрибированным звонкам: один сводный отчёт по выборке.
      </p>
      <div className="card table-wrap">
        {isLoading ? (
          <p className="empty">Загрузка...</p>
        ) : !data?.items.length ? (
          <p className="empty">Исследований пока нет. Создайте первое.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Название</th>
                <th>Фильтры</th>
                <th>Звонков</th>
                <th>Статус</th>
                <th>Автор</th>
                <th>Создано</th>
                <th className="col-actions">Действия</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/research/${r.id}`}>{r.title}</Link>
                  </td>
                  <td>{formatFilters(r.filters_json)}</td>
                  <td>{r.call_count || "—"}</td>
                  <td>
                    <span className={`badge ${statusClass(r.status)}`}>
                      {STATUS_LABEL[r.status] || r.status}
                    </span>
                  </td>
                  <td>{r.user_name || "—"}</td>
                  <td>{new Date(r.created_at).toLocaleString("ru")}</td>
                  <td>
                    {r.status === "completed" ? (
                      <a
                        href={`/api/v1/research/${r.id}/export?format=md`}
                        className="btn btn-icon"
                        title="Скачать отчёт"
                        aria-label="Скачать отчёт"
                      >
                        <Download size={16} />
                      </a>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-icon btn-icon-danger"
                      title="Удалить"
                      aria-label="Удалить"
                      onClick={() => {
                        if (window.confirm(`Удалить исследование «${r.title}»?`)) remove.mutate(r.id);
                      }}
                      disabled={remove.isPending}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
