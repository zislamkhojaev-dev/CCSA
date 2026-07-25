const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

export type CallExportFormat = "json" | "csv";

export type CallExportFiltersPayload = {
  status_filter?: string | null;
  operator_match?: string | null;
  operator_value?: string | null;
  client_match?: string | null;
  client_value?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  duration_op?: string | null;
  duration_value?: number | null;
  score_op?: string | null;
  score_value?: number | null;
  tag_id?: number | null;
};

export type CallExportJob = {
  id: number;
  format: CallExportFormat;
  status: string;
  message?: string | null;
  row_count: number;
  error_message?: string | null;
};

function filenameFromDisposition(disposition: string | null, fallback: string): string {
  const match = (disposition ?? "").match(/filename="([^"]+)"/);
  return match?.[1] ?? fallback;
}

async function triggerBlobDownload(res: Response, fallbackName: string): Promise<void> {
  const blob = await res.blob();
  const filename = filenameFromDisposition(res.headers.get("Content-Disposition"), fallbackName);
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function readError(res: Response): Promise<string> {
  const err = await res.json().catch(() => ({ detail: res.statusText }));
  const detail = err.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") || "Request failed";
  }
  return "Request failed";
}

/** Sync download for selected call ids. */
export async function downloadSelectedCallsExport(
  ids: number[],
  format: CallExportFormat,
): Promise<void> {
  const res = await fetch(`${API_BASE}/calls/export`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format, ids }),
  });
  if (!res.ok) throw new Error(await readError(res));
  await triggerBlobDownload(res, `calls.${format}`);
}

export async function startCallsExportJob(
  format: CallExportFormat,
  filters: CallExportFiltersPayload,
): Promise<CallExportJob> {
  const res = await fetch(`${API_BASE}/calls/export/jobs`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format, filters }),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function getCallsExportJob(jobId: number): Promise<CallExportJob> {
  const res = await fetch(`${API_BASE}/calls/export/jobs/${jobId}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function downloadCallsExportJob(jobId: number, format: CallExportFormat): Promise<void> {
  const res = await fetch(`${API_BASE}/calls/export/jobs/${jobId}/download`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await readError(res));
  await triggerBlobDownload(res, `calls-export-${jobId}.${format}`);
}

type WaitResult = { status: "completed" | "error"; error?: string; row_count?: number };

/** Wait for export job via SSE, with polling fallback. */
export function waitForCallsExportJob(jobId: number): Promise<WaitResult> {
  return new Promise((resolve, reject) => {
    let settled = false;
    let es: EventSource | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const finish = (result: WaitResult) => {
      if (settled) return;
      settled = true;
      if (es) es.close();
      if (pollTimer) clearInterval(pollTimer);
      resolve(result);
    };

    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      if (es) es.close();
      if (pollTimer) clearInterval(pollTimer);
      reject(err);
    };

    const checkStatus = async () => {
      try {
        const job = await getCallsExportJob(jobId);
        if (job.status === "completed") {
          finish({ status: "completed", row_count: job.row_count });
        } else if (job.status === "error") {
          finish({ status: "error", error: job.error_message || "Ошибка экспорта" });
        }
      } catch (e) {
        fail(e instanceof Error ? e : new Error("Не удалось получить статус экспорта"));
      }
    };

    try {
      es = new EventSource(`${API_BASE}/calls/export/jobs/${jobId}/events`, {
        withCredentials: true,
      });
      es.addEventListener("status", (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data) as {
            status?: string;
            error?: string;
            row_count?: number;
            done?: boolean;
          };
          if (data.status === "completed" || (data.done && !data.error && data.status !== "error")) {
            finish({ status: "completed", row_count: data.row_count });
          } else if (data.status === "error" || data.error) {
            finish({ status: "error", error: data.error || "Ошибка экспорта" });
          }
        } catch {
          /* ignore malformed ping payloads */
        }
      });
      es.onerror = () => {
        /* fall through to polling */
      };
    } catch {
      /* SSE unavailable */
    }

    pollTimer = setInterval(checkStatus, 5000);
    void checkStatus();
  });
}
