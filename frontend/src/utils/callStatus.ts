const PROCESSING = new Set(["pending", "transcribing", "transcribed", "analyzing"]);

export function isCallProcessing(status: string | undefined): boolean {
  return !!status && PROCESSING.has(status);
}

export function callStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "В очереди",
    transcribing: "Распознавание речи (ASR)…",
    transcribed: "Транскрипт готов, запуск анализа…",
    analyzing: "Анализ ИИ (LLM)…",
    analyzed: "Готово",
    error: "Ошибка обработки",
  };
  return labels[status] ?? status;
}

export function callStatusBanner(status: string, errorMessage?: string | null): string | null {
  if (status === "error" && errorMessage) {
    return `Ошибка: ${errorMessage}`;
  }
  if (isCallProcessing(status)) {
    return callStatusLabel(status);
  }
  return null;
}
