import type { ReactNode } from "react";
import { formatTime, sortUtterances, speakerClass, speakerLabel } from "../utils/transcript";

type Utterance = { speaker: string; text: string; start: number; end?: number };

type Props = {
  utterances?: Utterance[] | null;
  fullText?: string | null;
  onSeek?: (time: number) => void;
  renderText?: (text: string) => ReactNode;
  emptyMessage?: string;
};

export default function TranscriptList({
  utterances,
  fullText,
  onSeek,
  renderText,
  emptyMessage = "Транскрипт отсутствует.",
}: Props) {
  const sorted = sortUtterances(utterances);

  if (!sorted.length) {
    if (fullText?.trim()) {
      return <p className="transcript-full">{fullText}</p>;
    }
    return <p className="empty">{emptyMessage}</p>;
  }

  return (
    <>
      {sorted.map((u, i) => (
        <UtteranceBubble
          key={`${u.start}-${u.speaker}-${i}`}
          u={u}
          onSeek={onSeek}
          renderText={renderText}
        />
      ))}
    </>
  );
}

function UtteranceBubble({
  u,
  onSeek,
  renderText,
}: {
  u: Utterance;
  onSeek?: (time: number) => void;
  renderText?: (text: string) => ReactNode;
}) {
  const body = renderText ? renderText(u.text) : u.text;
  return (
    <div
      className={`transcript-bubble ${speakerClass(u.speaker)}`}
      onClick={() => onSeek?.(u.start)}
      role={onSeek ? "button" : undefined}
    >
      <div className="transcript-meta">
        <span className="transcript-time">{formatTime(u.start)}</span>
        <span className="transcript-speaker">{speakerLabel(u.speaker)}</span>
      </div>
      <div className="transcript-text">{body}</div>
    </div>
  );
}
