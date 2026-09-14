export type HighlightPart = { kind: "text" | "neg" | "pos"; value: string };

const TRIGGER_RE = /(плохо|ужас|мат|дурак|жалоб)|(спасибо|благодар|отлично|хорошо)/gi;

export function highlightTranscriptParts(text: string): HighlightPart[] {
  if (!text) return [];
  const parts: HighlightPart[] = [];
  let last = 0;
  for (const match of text.matchAll(TRIGGER_RE)) {
    const idx = match.index ?? 0;
    if (idx > last) {
      parts.push({ kind: "text", value: text.slice(last, idx) });
    }
    if (match[1]) {
      parts.push({ kind: "neg", value: match[1] });
    } else if (match[2]) {
      parts.push({ kind: "pos", value: match[2] });
    }
    last = idx + match[0].length;
  }
  if (last < text.length) {
    parts.push({ kind: "text", value: text.slice(last) });
  }
  return parts;
}
