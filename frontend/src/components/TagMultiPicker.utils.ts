import { api, type Paginated } from "../api/client";
import type { SearchableOption } from "./SearchableSelect";

type TagOut = { id: number; name: string };

export async function fetchTagOptions(q: string): Promise<SearchableOption[]> {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (q.trim()) params.set("q", q.trim());
  const data = await api.get<Paginated<TagOut>>(`/tags?${params}`);
  return data.items.map((t) => ({ id: t.id, label: t.name }));
}

export async function createTag(name: string): Promise<SearchableOption | null> {
  const tag = await api.post<TagOut>("/tags", { name });
  return { id: tag.id, label: tag.name };
}
