import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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

export default function OperatorsPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({
    queryKey: ["operators", page],
    queryFn: () => api.get<Paginated>(`/operators?page=${page}&page_size=20`),
  });

  const sync = async () => {
    await api.post("/operators/sync");
    alert("Синхронизация запущена");
  };

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Операторы</h1>
        <button type="button" className="btn btn-secondary" onClick={sync}>
          Синхронизировать с Webitel
        </button>
      </div>
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
      </div>
    </>
  );
}
