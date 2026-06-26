import { api } from "../api/client";
import type { SearchableOption } from "./SearchableSelect";

type TagOut = { id: number; name: string };

export async function fetchTagOptions(q: string): Promise<SearchableOption[]> {
  const params = new URLSearchParams({ limit: "50" });
  if (q.trim()) params.set("q", q.trim());
  const items = await api.get<TagOut[]>(`/tags?${params}`);
  return items.map((t) => ({ id: t.id, label: t.name }));
}

export async function createTag(name: string): Promise<SearchableOption | null> {
  const tag = await api.post<TagOut>("/tags", { name });
  return { id: tag.id, label: tag.name };
}
