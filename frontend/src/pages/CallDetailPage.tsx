import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, scoreBadge } from "../api/client";
import AudioWaveform from "../components/AudioWaveform";
import CriteriaChecklist from "../components/CriteriaChecklist";
import TranscriptList from "../components/TranscriptList";
import { callStatusBanner, callStatusLabel, isCallProcessing } from "../utils/callStatus";
import { exportCallTranscript } from "../utils/exportTranscript";
import TagMultiPicker, { type TagItem } from "../components/TagMultiPicker";
import { sortUtterances } from "../utils/transcript";

type Utterance = { speaker: string; text: string; start: number; end: number };

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

export default function CallDetailPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const seekRef = useRef<(t: number) => void>(() => {});
  const [note, setNote] = useState("");
  const [tags, setTags] = useState<TagItem[]>([]);
  const [actionHint, setActionHint] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["call", id],
    queryFn: () => api.get<CallDetail>(`/calls/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (isCallProcessing(q.state.data?.status) ? 2000 : false),
  });

  const processing = isCallProcessing(data?.status);
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

  if (isLoading || !data) return <p className="empty">Загрузка...</p>;

  const analysis = data.analysis_results[0];
  const trans = data.transcriptions[0];
  const utterances = sortUtterances((trans?.utterances as Utterance[]) || []);
  const scoreClass = scoreBadge(analysis?.total_score);
  const busy = processing || reanalyze.isPending || retranscribe.isPending;
  const hasTranscript = utterances.length > 0 || Boolean(trans?.full_text?.trim());

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
      utterances
    );
    if (!ok) setActionHint("Нет текста расшифровки для экспорта");
  };

  return (
    <>
      <h1 className="page-title">Звонок #{data.id}</h1>

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

      <div className="grid-3">
        <div className="card">
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>ID: {data.id} · {data.call_uuid}</p>
          <p><strong>Оператор:</strong> {data.operator_name || "—"}</p>
          <p><strong>Клиент:</strong> {data.client_number || "—"}</p>
          <p><strong>Дата:</strong> {data.call_timestamp ? new Date(data.call_timestamp).toLocaleString("ru") : "—"}</p>
          <p><strong>Длительность:</strong> {data.duration ? `${data.duration} с` : "—"}</p>
          <p>
            <strong>Статус:</strong>{" "}
            <span className={`badge ${processing ? "badge-yellow" : data.status === "error" ? "badge-red" : "badge-gray"}`}>
              {callStatusLabel(data.status)}
            </span>
          </p>
          {data.error_message && (
            <p style={{ color: "var(--red)", fontSize: "0.85rem" }}><strong>Ошибка:</strong> {data.error_message}</p>
          )}
          {trans && (
            <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
              ASR: {trans.model_name || "—"}
              {trans.model_name === "mock" && " (модель не загружена — см. логи stt-service)"}
            </p>
          )}
          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "1rem 0" }} />
          <p className={`score-big ${scoreClass}`}>
            {analysis?.total_score != null ? `${analysis.total_score}/100` : "—"}
          </p>
          {analysis && !processing && (
            <>
              <h4 style={{ marginTop: "1rem" }}>ИИ-суммаризация</h4>
              <p>{analysis.summary}</p>
              <p><strong>Боли клиента:</strong> {analysis.client_pains || "—"}</p>
              <p><strong>Итог:</strong> {analysis.call_outcome || "—"}</p>
            </>
          )}
          {processing && (
            <p style={{ color: "var(--muted)", fontSize: "0.875rem", marginTop: "1rem" }}>
              Суммаризация и чек-лист обновятся после завершения обработки.
            </p>
          )}
          <h4 style={{ marginTop: "1rem" }}>Чек-лист</h4>
          <CriteriaChecklist criteria={analysis?.criteria_results} />
        </div>

        <div className="card">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
              marginBottom: "0.5rem",
            }}
          >
            <h4 style={{ margin: 0 }}>Расшифровка</h4>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleExportTranscript}
              disabled={!hasTranscript || busy}
              title={hasTranscript ? "Скачать текст диалога (.txt)" : "Транскрипт ещё не готов"}
            >
              Экспорт расшифровки
            </button>
          </div>
          <AudioWaveform
            audioUrl={data.audio_url}
            utterances={utterances}
            onSeek={(t) => seekRef.current(t)}
            onRegisterSeek={(seek) => {
              seekRef.current = seek;
            }}
          />
          <div style={{ maxHeight: 480, overflowY: "auto", marginTop: "1rem" }}>
            <TranscriptList
              utterances={utterances}
              fullText={trans?.full_text}
              onSeek={(t) => seekRef.current(t)}
              renderText={(text) => <span dangerouslySetInnerHTML={{ __html: highlightText(text) }} />}
              emptyMessage={
                processing
                  ? "Транскрипт появится после распознавания…"
                  : "Транскрипт отсутствует. Запустите «Повторное распознавание (ASR)»."
              }
            />
          </div>
        </div>

        <div className="card">
          <h4>Теги</h4>
          <TagMultiPicker value={tags} onChange={setTags} disabled={busy} />
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => saveTags.mutate()}
            disabled={busy}
            style={{ marginTop: "0.75rem" }}
          >
            Сохранить теги
          </button>
          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "1rem 0" }} />
          <h4>Комментарий супервизора</h4>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Ваш комментарий..."
            style={{ width: "100%", minHeight: 80, margin: "0.5rem 0" }}
            disabled={busy}
          />
          <button type="button" className="btn btn-primary" onClick={() => addNote.mutate()} disabled={!note.trim() || busy}>
            Добавить
          </button>
          {data.notes.map((n) => (
            <div key={n.id} style={{ marginTop: "0.75rem", fontSize: "0.875rem" }}>
              <strong>{n.user_name}</strong> ({new Date(n.created_at).toLocaleString("ru")}): {n.text}
            </div>
          ))}
          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "1rem 0" }} />
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => retranscribe.mutate()}
            disabled={busy}
            style={{ marginBottom: "0.5rem", width: "100%" }}
          >
            {retranscribe.isPending || data.status === "transcribing"
              ? "Распознавание ASR…"
              : "Повторное распознавание (ASR)"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => reanalyze.mutate()}
            disabled={busy}
            style={{ width: "100%" }}
          >
            {reanalyze.isPending || data.status === "analyzing"
              ? "Анализ LLM…"
              : "Повторный анализ (LLM)"}
          </button>
        </div>
      </div>
    </>
  );
}
