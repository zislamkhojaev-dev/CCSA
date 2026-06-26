import { formatTime, sortUtterances, speakerLabel, type Utterance } from "./transcript";

export type TranscriptExportMeta = {
  callId: number;
  operatorName?: string | null;
  clientNumber?: string | null;
  callTimestamp?: string | null;
  durationSec?: number | null;
};

export function buildTranscriptText(
  meta: TranscriptExportMeta,
  fullText: string | null | undefined,
  utterances: Utterance[] | null | undefined
): string {
  const lines: string[] = [];
  lines.push(`Звонок #${meta.callId}`);
  if (meta.operatorName) lines.push(`Оператор: ${meta.operatorName}`);
  if (meta.clientNumber) lines.push(`Клиент: ${meta.clientNumber}`);
  if (meta.callTimestamp) {
    lines.push(`Дата: ${new Date(meta.callTimestamp).toLocaleString("ru")}`);
  }
  if (meta.durationSec != null) lines.push(`Длительность: ${meta.durationSec} с`);
  lines.push("");

  const sorted = sortUtterances(utterances);
  if (sorted.length > 0) {
    for (const u of sorted) {
      const time = formatTime(u.start);
      lines.push(`[${time}] ${speakerLabel(u.speaker)}: ${u.text}`);
    }
  } else if (fullText?.trim()) {
    lines.push(fullText.trim());
  } else {
    return "";
  }

  return lines.join("\n");
}

export function downloadTextFile(filename: string, content: string): void {
  const blob = new Blob(["\uFEFF" + content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function exportCallTranscript(
  meta: TranscriptExportMeta,
  fullText: string | null | undefined,
  utterances: Utterance[] | null | undefined
): boolean {
  const text = buildTranscriptText(meta, fullText, utterances);
  if (!text) return false;
  downloadTextFile(`call-${meta.callId}-transcript.txt`, text);
  return true;
}
