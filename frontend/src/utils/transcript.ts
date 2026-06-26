export type Utterance = { speaker: string; text: string; start: number; end?: number };

const SPEAKER_RANK: Record<string, number> = { client: 0, agent: 1, mixed: 2 };

export function sortUtterances<T extends Utterance>(items: T[] | null | undefined): T[] {
  if (!items?.length) return [];
  return [...items].sort((a, b) => {
    const ds = (a.start ?? 0) - (b.start ?? 0);
    if (ds !== 0) return ds;
    const de = (a.end ?? 0) - (b.end ?? 0);
    if (de !== 0) return de;
    return (SPEAKER_RANK[a.speaker] ?? 2) - (SPEAKER_RANK[b.speaker] ?? 2);
  });
}

export function formatTime(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function speakerClass(speaker: string): string {
  if (speaker === "agent") return "agent";
  if (speaker === "client") return "client";
  return "mixed";
}

export function speakerLabel(speaker: string): string {
  if (speaker === "agent") return "Оператор";
  if (speaker === "client") return "Клиент";
  return "Диалог";
}
