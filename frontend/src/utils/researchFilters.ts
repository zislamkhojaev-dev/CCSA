export function formatResearchFilters(f: Record<string, unknown>): string {
  const parts: string[] = [];
  if (f.date_from) parts.push(`от ${f.date_from}`);
  if (f.date_to) parts.push(`до ${f.date_to}`);
  if (f.direction === "inbound") parts.push("входящие");
  if (f.direction === "outbound") parts.push("исходящие");
  if (f.operator_id) parts.push(`оператор #${f.operator_id}`);
  if (f.queue) parts.push(`очередь «${f.queue}»`);
  if (f.tag) parts.push(`тег «${f.tag}»`);
  if (f.score_op && f.score_value != null && f.score_value !== "") {
    const op = f.score_op === "eq" ? "=" : f.score_op === "lt" ? "<" : ">";
    parts.push(`оценка ${op} ${f.score_value}%`);
  }
  return parts.length ? parts.join(", ") : "все звонки";
}

export type ResearchProgress = {
  status?: string;
  phase?: string;
  step?: string;
  call_count?: number;
  batch?: number;
  batch_total?: number;
  error?: string;
  done?: boolean;
};

export function researchProgressLabel(p: ResearchProgress | null): string {
  if (!p) return "Идёт анализ…";
  if (p.status === "error") return p.error || "Ошибка анализа";
  if (p.phase === "starting") return "Запуск…";
  if (p.phase === "loaded") {
    return p.call_count != null
      ? `Загружено ${p.call_count} звонков, подготовка LLM…`
      : "Подготовка данных…";
  }
  if (p.step === "single") return "LLM: сводный анализ выборки…";
  if (p.step === "map" && p.batch != null && p.batch_total != null) {
    return `LLM: часть ${p.batch} из ${p.batch_total}…`;
  }
  if (p.step === "reduce") return "LLM: финальный отчёт…";
  if (p.step === "prepare") return "Подготовка транскриптов…";
  return "Идёт анализ…";
}
