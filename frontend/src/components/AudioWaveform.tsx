import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { sortUtterances } from "../utils/transcript";

type Props = {
  audioUrl: string | null;
  utterances?: { speaker: string; start: number; end: number; text?: string }[];
  onSeek?: (time: number) => void;
  onRegisterSeek?: (seek: (time: number) => void) => void;
  height?: number;
};

function readCssColor(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function AudioWaveform({
  audioUrl,
  utterances = [],
  onSeek,
  onRegisterSeek,
  height = 72,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const onSeekRef = useRef(onSeek);
  const onRegisterSeekRef = useRef(onRegisterSeek);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    onSeekRef.current = onSeek;
  }, [onSeek]);

  useEffect(() => {
    onRegisterSeekRef.current = onRegisterSeek;
  }, [onRegisterSeek]);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!audioUrl || !containerRef.current) return;

    wsRef.current?.destroy();
    setLoading(true);
    setPlaying(false);
    setCurrent(0);
    setDuration(0);

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: readCssColor("--muted", "#5c6169"),
      progressColor: readCssColor("--primary", "#2d2f33"),
      cursorColor: readCssColor("--primary", "#2d2f33"),
      height,
      url: audioUrl,
      fetchParams: { credentials: "include" },
      backend: "MediaElement",
      normalize: false,
    });
    wsRef.current = ws;

    const seek = (time: number) => {
      ws.setTime(time);
      setCurrent(time);
      onSeekRef.current?.(time);
    };
    onRegisterSeekRef.current?.(seek);

    ws.on("ready", () => {
      setDuration(ws.getDuration());
      setLoading(false);
    });
    ws.on("timeupdate", (t) => setCurrent(t));
    ws.on("play", () => setPlaying(true));
    ws.on("pause", () => setPlaying(false));
    ws.on("finish", () => setPlaying(false));
    ws.on("interaction", () => {
      const t = ws.getCurrentTime();
      setCurrent(t);
      onSeekRef.current?.(t);
    });
    ws.on("error", () => setLoading(false));

    return () => {
      onRegisterSeekRef.current?.(() => {});
      ws.destroy();
    };
  }, [audioUrl, height]);

  const markers = sortUtterances(utterances).filter((u) =>
    /плохо|ужас|мат|жалоб|спасибо|благодар/i.test(u.text || "")
  );

  if (!audioUrl) {
    return <p className="text-muted text-sm">Аудиозапись недоступна для воспроизведения.</p>;
  }

  return (
    <div className="audio-waveform">
      <div ref={containerRef} className="audio-waveform__canvas" />
      <div className="audio-waveform__controls">
        <button
          type="button"
          className="btn btn-secondary audio-waveform__play"
          onClick={() => wsRef.current?.playPause()}
          disabled={loading}
          aria-label={playing ? "Пауза" : "Воспроизведение"}
        >
          {playing ? "⏸" : "▶"}
        </button>
        <span className="audio-waveform__time">
          {formatTime(current)} / {duration > 0 ? formatTime(duration) : "—"}
        </span>
        {loading && <span className="audio-waveform__loading">Загрузка…</span>}
      </div>
      {markers.length > 0 && (
        <div className="audio-waveform__markers">
          <span className="audio-waveform__markers-label">Триггеры:</span>
          {markers.map((m, i) => (
            <button
              key={i}
              type="button"
              className="btn btn-secondary audio-waveform__marker-btn"
              onClick={() => {
                wsRef.current?.setTime(m.start);
                setCurrent(m.start);
                onSeekRef.current?.(m.start);
              }}
            >
              {m.start.toFixed(1)}s
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
