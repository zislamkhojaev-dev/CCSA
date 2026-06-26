import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Copy, Pencil, Trash2 } from "lucide-react";
import { api } from "../api/client";

type Scenario = {
  id: number;
  name: string;
  llm_model: string;
  is_active: boolean;
  criteria_count: number;
  updated_at: string;
};

export default function ScenariosPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/scenarios/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scenarios"] }),
  });

  const copy = useMutation({
    mutationFn: (id: number) => api.post<Scenario>(`/scenarios/${id}/copy`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scenarios"] }),
  });

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
        <h1 className="page-title">Сценарии и критерии</h1>
        <Link to="/scenarios/new" className="btn btn-primary">
          Новый сценарий
        </Link>
      </div>
      <div className="card table-wrap">
        {isLoading ? (
          <p className="empty">Загрузка...</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Название</th>
                <th>Критериев</th>
                <th>LLM</th>
                <th>Статус</th>
                <th>Изменён</th>
                <th className="col-actions">Действия</th>
              </tr>
            </thead>
            <tbody>
              {data?.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link to={`/scenarios/${s.id}`}>{s.name}</Link>
                  </td>
                  <td>{s.criteria_count}</td>
                  <td>{s.llm_model}</td>
                  <td>
                    <span className={`badge ${s.is_active ? "badge-green" : "badge-gray"}`}>
                      {s.is_active ? "Активен" : "Выключен"}
                    </span>
                  </td>
                  <td>{new Date(s.updated_at).toLocaleDateString("ru")}</td>
                  <td>
                    <div className="table-actions" role="group" aria-label="Действия">
                      <Link
                        to={`/scenarios/${s.id}`}
                        className="btn btn-icon btn-secondary"
                        title="Редактировать"
                        aria-label="Редактировать"
                      >
                        <Pencil size={16} />
                      </Link>
                      <button
                        type="button"
                        className="btn btn-icon btn-secondary"
                        title="Копировать"
                        aria-label="Копировать"
                        onClick={() => copy.mutate(s.id)}
                        disabled={copy.isPending}
                      >
                        <Copy size={16} />
                      </button>
                      <a
                        href={`/api/v1/scenarios/${s.id}/export`}
                        className="btn btn-icon btn-secondary"
                        title="Экспорт"
                        aria-label="Экспорт"
                      >
                        <ArrowUp size={16} />
                      </a>
                      <button
                        type="button"
                        className="btn btn-icon btn-icon-danger"
                        title="Удалить"
                        aria-label="Удалить"
                        onClick={() => {
                          if (window.confirm(`Удалить сценарий «${s.name}»?`)) remove.mutate(s.id);
                        }}
                        disabled={remove.isPending}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
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
