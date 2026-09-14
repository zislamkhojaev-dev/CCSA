const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

export type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

function errorMessageFromBody(err: Record<string, unknown>, fallback: string): string {
  if (typeof err.message === "string" && err.message) return err.message;
  const detail = err.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") || fallback;
  }
  return fallback;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (res.status === 401 && !path.includes("/auth/login")) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorMessageFromBody(err, "Request failed"));
  }
  if (res.status === 204) return {} as T;
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: async (path: string, formData: FormData) => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      body: formData,
      credentials: "include",
    });
    if (!res.ok) throw new Error("Upload failed");
    return res.json();
  },
};

export function scoreBadge(score: number | null | undefined): "green" | "yellow" | "red" | "gray" {
  if (score == null) return "gray";
  if (score >= 80) return "green";
  if (score >= 50) return "yellow";
  return "red";
}
