import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api } from "../api/client";
import ScoreBadge from "../components/ScoreBadge";

type Operator = {
  id: number;
  full_name: string;
  team_name: string | null;
  is_active: boolean;
  calls_count: number;
  avg_score: number | null;
};

type Paginated = { items: Operator[]; total: number };

type SyncResult = { message: string; created: number; found: number; calls_scanned: number };

const PAGE_SIZE = 20;

export default function OperatorsPage() {
  const [page, setPage] = useState(1);
  const qc = useQueryClient();
  const [syncStatus, setSyncStatus] = useState<{ text: string; error: boolean } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["operators", page],
    queryFn: () => api.get<Paginated>(`/operators?page=${page}&page_size=${PAGE_SIZE}`),
  });

  const sync = useMutation({
    mutationFn: () => api.post<SyncResult>("/operators/sync"),
    onSuccess: (r) => {
      setSyncStatus({ text: r.message, error: false });
      if (r.created > 0) qc.invalidateQueries({ queryKey: ["operators"] });
    },
    onError: (e: Error) => setSyncStatus({ text: e.message, error: true }),
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Операторы</h1>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            setSyncStatus(null);
            sync.mutate();
          }}
          disabled={sync.isPending}
        >
          <RefreshCw size={16} className={sync.isPending ? "icon-spin" : undefined} aria-hidden />
          {sync.isPending ? "Обновление…" : "Обновить список операторов"}
        </button>
      </div>
      {syncStatus && (
        <p
          className={`form-hint mb-3 ${syncStatus.error ? "text-error" : ""}`}
          role="status"
          aria-live="polite"
        >
          {syncStatus.text}
        </p>
      )}
      <div className="card table-wrap">
        {isLoading ? (
          <p className="empty">Загрузка...</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Имя</th>
                <th>Команда</th>
                <th>Звонков</th>
                <th>Средний балл</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((op) => (
                <tr key={op.id}>
                  <td>{op.full_name}</td>
                  <td>{op.team_name || "—"}</td>
                  <td>{op.calls_count}</td>
                  <td>
                    <ScoreBadge score={op.avg_score} />
                  </td>
                  <td>
                    <span className={`badge ${op.is_active ? "badge-green" : "badge-gray"}`}>
                      {op.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {(data?.total ?? 0) > 0 && (
          <div className="pagination">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
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
          </div>
        )}
      </div>
    </>
  );
}
