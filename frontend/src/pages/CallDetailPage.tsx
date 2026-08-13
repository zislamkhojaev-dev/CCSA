import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, FileDown } from "lucide-react";
import { api, scoreBadge } from "../api/client";
import AudioWaveform from "../components/AudioWaveform";
import CriteriaChecklist from "../components/CriteriaChecklist";
import TranscriptList from "../components/TranscriptList";
import { callStatusBanner, callStatusLabel, isCallProcessing } from "../utils/callStatus";
import { exportCallTranscript } from "../utils/exportTranscript";
import TagMultiPicker, { type TagItem } from "../components/TagMultiPicker";
import { sortUtterances } from "../utils/transcript";

type Utterance = { speaker: string; start: number; end: number; text: string };

type CallDetail = {
  id: number;
  call_uuid: string;
  operator_name: string | null;
  client_number: string | null;
  call_timestamp: string | null;
  duration: number | null;
  status: string;
  error_message: string | null;
  audio_url: string | null;
  tags: { id: number; name: string }[];
  transcriptions: { full_text: string | null; utterances: Utterance[] | null; model_name: string | null }[];
  analysis_results: {
    total_score: number | null;
    summary: string | null;
    client_pains: string | null;
    call_outcome: string | null;
    topic: string | null;
    criteria_results: Record<string, { score: number; passed: boolean; comment: string; status?: string }>;
  }[];
  notes: { id: number; text: string; user_name: string; created_at: string }[];
};

function highlightText(text: string) {
  const negative = /(плохо|ужас|мат|дурак|жалоб)/gi;
  const positive = /(спасибо|благодар|отлично|хорошо)/gi;
  return text
    .replace(negative, (m) => `<span class="trigger-negative">${m}</span>`)
    .replace(positive, (m) => `<span class="trigger-positive">${m}</span>`);
}

function formatDuration(sec: number | null): string {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}м ${s}с` : `${s}с`;
}

export default function CallDetailPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const seekRef = useRef<(t: number) => void>(() => {});
  const [note, setNote] = useState("");
  const [tags, setTags] = useState<TagItem[]>([]);
  const [actionHint, setActionHint] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["call", id],
    queryFn: () => api.get<CallDetail>(`/calls/${id}`),
    enabled: !!id,
  });

  const processing = isCallProcessing(data?.status);
  const { data: liveStatus } = useQuery({
    queryKey: ["call-status", id],
    queryFn: () =>
      api.get<{ id: number; status: string; error_message: string | null }>(`/calls/${id}/status`),
    enabled: !!id && processing,
    refetchInterval: 2000,
  });

  useEffect(() => {
    if (liveStatus && data && liveStatus.status !== data.status) {
      qc.invalidateQueries({ queryKey: ["call", id] });
    }
  }, [liveStatus, data, id, qc]);
  const statusBanner = data ? callStatusBanner(data.status, data.error_message) : null;

  useEffect(() => {
    if (data) setTags(data.tags.map((t) => ({ id: t.id, name: t.name })));
  }, [data]);

  useEffect(() => {
    if (!processing) setActionHint(null);
  }, [processing, data?.status]);

  const saveTags = useMutation({
    mutationFn: () => api.patch(`/calls/${id}/tags`, { tag_ids: tags.map((t) => t.id) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["call", id] }),
  });

  const addNote = useMutation({
    mutationFn: () => api.post(`/calls/${id}/notes`, { text: note }),
    onSuccess: () => {
      setNote("");
      qc.invalidateQueries({ queryKey: ["call", id] });
    },
  });

  const reanalyze = useMutation({
    mutationFn: () => api.post(`/calls/${id}/reanalyze`),
    onSuccess: () => {
      setActionHint("Повторный анализ LLM запущен…");
      qc.invalidateQueries({ queryKey: ["call", id] });
    },
    onError: (e: Error) => setActionHint(e.message || "Не удалось запустить анализ"),
  });

  const retranscribe = useMutation({
    mutationFn: () => api.post(`/calls/${id}/retranscribe`),
    onSuccess: () => {
      setActionHint("Повторное распознавание ASR запущено…");
      qc.invalidateQueries({ queryKey: ["call", id] });
    },
    onError: (e: Error) => setActionHint(e.message || "Не удалось запустить ASR"),
  });

  const renderHighlighted = useCallback(
    (text: string) => <span dangerouslySetInnerHTML={{ __html: highlightText(text) }} />,
    [],
  );

  const utterances = useMemo(
    () => sortUtterances((data?.transcriptions[0]?.utterances as Utterance[]) || []),
    [data?.transcriptions],
  );

  if (isLoading) return <p className="empty">Загрузка...</p>;

  if (isError) {
    return (
      <p className="empty text-error">
        Не удалось загрузить звонок: {error instanceof Error ? error.message : "ошибка сервера"}
      </p>
    );
  }

  if (!data) return <p className="empty">Звонок не найден</p>;

  const analysis = data.analysis_results[0];
  const trans = data.transcriptions[0];
  const scoreClass = scoreBadge(analysis?.total_score);
  const busy = processing || reanalyze.isPending || retranscribe.isPending;
  const hasTranscript = utterances.length > 0 || Boolean(trans?.full_text?.trim());

  const statusBadgeClass = processing
    ? "badge-yellow"
    : data.status === "error"
      ? "badge-red"
      : data.status === "analyzed"
        ? "badge-green"
        : "badge-gray";

  const handleExportTranscript = () => {
    const ok = exportCallTranscript(
      {
        callId: data.id,
        operatorName: data.operator_name,
        clientNumber: data.client_number,
        callTimestamp: data.call_timestamp,
        durationSec: data.duration,
      },
      trans?.full_text,
      utterances,
    );
    if (!ok) setActionHint("Нет текста расшифровки для экспорта");
  };

  const copyUuid = async () => {
    try {
      await navigator.clipboard.writeText(data.call_uuid);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setActionHint("Не удалось скопировать UUID");
    }
  };

  return (
    <div className="call-detail">
      <Link to="/calls" className="back-link">
        ← К списку звонков
      </Link>

      <header className="call-detail-header">
        <div className="call-detail-header-main">
          <div className="call-detail-title-row">
            <h1 className="page-title call-detail-title">Звонок #{data.id}</h1>
            <p className={`call-detail-score score-big ${scoreClass}`}>
              {analysis?.total_score != null ? `${analysis.total_score}/100` : "—"}
            </p>
            <span className={`badge ${statusBadgeClass}`}>{callStatusLabel(data.status)}</span>
            {analysis?.topic && <span className="badge badge-gray">{analysis.topic}</span>}
          </div>
          <p className="call-detail-meta">
            <span>{data.operator_name || "Оператор —"}</span>
            <span className="call-detail-meta-sep" aria-hidden>
              ·
            </span>
            <span>{data.client_number || "Клиент —"}</span>
            <span className="call-detail-meta-sep" aria-hidden>
              ·
            </span>
            <span>
              {data.call_timestamp ? new Date(data.call_timestamp).toLocaleString("ru") : "—"}
            </span>
            <span className="call-detail-meta-sep" aria-hidden>
              ·
            </span>
            <span>{formatDuration(data.duration)}</span>
            {trans?.model_name && (
              <>
                <span className="call-detail-meta-sep" aria-hidden>
                  ·
                </span>
                <span
                  className="call-detail-asr"
                  title={
                    trans.model_name === "mock"
                      ? `${trans.model_name} (модель не загружена — см. логи stt-service)`
                      : trans.model_name
                  }
                >
                  ASR: {trans.model_name.split("/").pop() || trans.model_name}
                </span>
              </>
            )}
            <button
              type="button"
              className="btn btn-secondary btn-icon call-detail-copy-uuid"
              onClick={copyUuid}
              title={copied ? "Скопировано" : "Копировать UUID"}
              aria-label={copied ? "UUID скопирован" : "Копировать UUID"}
            >
              <Copy size={14} />
            </button>
            {copied && <span className="text-hint">Скопировано</span>}
          </p>
        </div>

        <div className="call-detail-header-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleExportTranscript}
            disabled={!hasTranscript || busy}
            title={hasTranscript ? "Скачать текст диалога (.txt)" : "Транскрипт ещё не готов"}
          >
            <FileDown size={14} aria-hidden />
            Экспорт
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => retranscribe.mutate()}
            disabled={busy}
          >
            {retranscribe.isPending || data.status === "transcribing" ? "ASR…" : "Повтор ASR"}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => reanalyze.mutate()}
            disabled={busy}
          >
            {reanalyze.isPending || data.status === "analyzing" ? "LLM…" : "Повтор LLM"}
          </button>
        </div>
      </header>

      {(statusBanner || actionHint) && (
        <div
          className={`status-banner ${data.status === "error" ? "status-banner-error" : "status-banner-info"}`}
          role="status"
        >
          {(retranscribe.isPending || reanalyze.isPending || processing) && (
            <span className="status-spinner" aria-hidden />
          )}
          <span>{statusBanner || actionHint}</span>
        </div>
      )}

      {data.error_message && data.status === "error" && (
        <p className="text-error call-detail-error">
          <strong>Ошибка:</strong> {data.error_message}
        </p>
      )}

      <div className="call-detail-grid">
        <aside className="call-detail-analysis">
          <section className="card call-detail-section">
            <h3 className="call-detail-section-title">Вердикт</h3>
            {analysis && !processing ? (
              <>
                {analysis.call_outcome && (
                  <div className="call-detail-outcome">
                    <span className="call-detail-label">Итог</span>
                    <p>{analysis.call_outcome}</p>
                  </div>
                )}
                {analysis.summary && (
                  <div className="call-detail-block">
                    <span className="call-detail-label">Суммаризация</span>
                    <p>{analysis.summary}</p>
                  </div>
                )}
                {analysis.client_pains && (
                  <div className="call-detail-block">
                    <span className="call-detail-label">Боли клиента</span>
                    <p>{analysis.client_pains}</p>
                  </div>
                )}
              </>
            ) : (
              <p className="text-hint">
                {processing
                  ? "Суммаризация и чек-лист обновятся после завершения обработки."
                  : "Анализ ещё не выполнен."}
              </p>
            )}
          </section>

          <section className="card call-detail-section">
            <h3 className="call-detail-section-title">Теги</h3>
            <TagMultiPicker value={tags} onChange={setTags} disabled={busy} />
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => saveTags.mutate()}
              disabled={busy || saveTags.isPending}
            >
              {saveTags.isPending ? "Сохранение…" : "Сохранить теги"}
            </button>
          </section>

          <section className="card call-detail-section">
            <h3 className="call-detail-section-title">Комментарии</h3>
            <textarea
              className="form-input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Ваш комментарий…"
              rows={3}
              disabled={busy}
            />
            <button
              type="button"
              className="btn btn-primary btn-sm"
              style={{ marginTop: "var(--space-2)" }}
              onClick={() => addNote.mutate()}
              disabled={!note.trim() || busy || addNote.isPending}
            >
              Добавить
            </button>
            {data.notes.map((n) => (
              <div key={n.id} className="note-item">
                <strong>{n.user_name}</strong> ({new Date(n.created_at).toLocaleString("ru")}): {n.text}
              </div>
            ))}
          </section>
        </aside>

        <section className="card call-detail-transcript">
          <div className="card-header">
            <h3 className="call-detail-section-title">Расшифровка</h3>
          </div>
          <AudioWaveform
            audioUrl={data.audio_url}
            utterances={utterances}
            onSeek={(t) => seekRef.current(t)}
            onRegisterSeek={(seek) => {
              seekRef.current = seek;
            }}
          />
          <div className="scroll-panel call-detail-transcript-scroll">
            <TranscriptList
              utterances={utterances}
              fullText={trans?.full_text}
              onSeek={(t) => seekRef.current(t)}
              renderText={renderHighlighted}
              emptyMessage={
                processing
                  ? "Транскрипт появится после распознавания…"
                  : "Транскрипт отсутствует. Запустите «Повтор ASR»."
              }
            />
          </div>
        </section>

        <aside className="call-detail-sidebar">
          <section className="card call-detail-section call-detail-checklist">
            <h3 className="call-detail-section-title">Чек-лист</h3>
            <CriteriaChecklist
              criteria={analysis?.criteria_results}
              emptyMessage={processing ? "Чек-лист появится после анализа…" : "Нет данных чек-листа"}
            />
          </section>
        </aside>
      </div>
    </div>
  );
}
