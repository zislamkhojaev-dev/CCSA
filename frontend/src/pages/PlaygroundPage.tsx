import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { usePlayground } from "../context/PlaygroundContext";
import AudioWaveform from "../components/AudioWaveform";
import CriteriaChecklist from "../components/CriteriaChecklist";
import TranscriptList from "../components/TranscriptList";
import { sortUtterances } from "../utils/transcript";
import ScoreBadge from "../components/ScoreBadge";

type Scenario = { id: number; name: string };
type PlaygroundFile = {
  id: number;
  filename: string;
  status: string;
  error_message?: string | null;
  audio_url?: string | null;
  transcription?: { full_text?: string; utterances?: { speaker: string; text: string; start: number }[] };
  analysis?: {
    total_score?: number;
    summary?: string;
    client_pains?: string;
    call_outcome?: string;
    criteria_results?: Record<string, unknown>;
  };
};
type Job = { id: number; status: string; files: PlaygroundFile[] };

const STATUS_LABEL: Record<string, string> = {
  queued: "В очереди",
  transcribing: "Распознавание ASR",
  analyzing: "Анализ LLM",
  ready: "Готово",
  error: "Ошибка",
};

function isProcessing(job: Job | undefined): boolean {
  if (!job) return false;
  if (job.status === "processing") return true;
  return job.files.some((f) => f.status === "transcribing" || f.status === "analyzing");
}

export default function PlaygroundPage() {
  const {
    jobId,
    setJobId,
    scenarioId,
    setScenarioId,
    selectedFileId,
    setSelectedFileId,
    useScenarioPrompt,
    setUseScenarioPrompt,
    customPrompt,
    setCustomPrompt,
    clearSession,
  } = usePlayground();

  const [selected, setSelected] = useState<PlaygroundFile | null>(null);
  const seekRef = useRef<(time: number) => void>(() => {});
  const [progress, setProgress] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionHint, setActionHint] = useState<string | null>(null);

  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });

  const { data: job, refetch } = useQuery({
    queryKey: ["playground", jobId],
    queryFn: () => api.get<Job>(`/playground/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => (isProcessing(q.state.data) ? 2000 : false),
  });

  useEffect(() => {
    if (!jobId) return;
    const es = new EventSource(`/api/v1/playground/jobs/${jobId}/events`, { withCredentials: true });
    es.onmessage = () => refetch();
    es.addEventListener("status", () => refetch());
    return () => es.close();
  }, [jobId, refetch]);

  useEffect(() => {
    if (!job?.files.length) {
      setSelected(null);
      return;
    }
    const match = selectedFileId
      ? job.files.find((f) => f.id === selectedFileId)
      : undefined;
    setSelected(match ?? job.files[0] ?? null);
  }, [job, selectedFileId]);

  useEffect(() => {
    if (!job?.files.length) {
      setProgress(0);
      return;
    }
    const done = job.files.filter((f) => f.status === "ready" || f.status === "error").length;
    setProgress(Math.round((done / job.files.length) * 100));
  }, [job?.files]);

  const createJob = useMutation({
    mutationFn: () =>
      api.post<Job>("/playground/jobs", {
        scenario_id: scenarioId || null,
        use_scenario_prompt: useScenarioPrompt,
        custom_prompt: useScenarioPrompt ? null : customPrompt,
      }),
    onSuccess: (j) => {
      setJobId(j.id);
      setActionError(null);
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const runAnalysis = useMutation({
    mutationFn: () => api.post<{ message: string }>(`/playground/jobs/${jobId}/run`),
    onSuccess: () => {
      setActionError(null);
      refetch();
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const canRun =
    !!job?.files.length &&
    job.files.some((f) => f.status === "queued" || f.status === "error") &&
    !isProcessing(job) &&
    !runAnalysis.isPending;

  const readyFilesCount = job?.files.filter((f) => f.status === "ready").length ?? 0;

  const promoteAll = useMutation({
    mutationFn: () => api.post<{ message: string }>(`/playground/jobs/${jobId}/promote-to-calls`),
    onSuccess: (res) => {
      setActionError(null);
      setActionHint(res.message);
    },
    onError: (e: Error) => {
      setActionHint(null);
      setActionError(e.message);
    },
  });

  const onDrop = useCallback(
    async (files: FileList | null) => {
      if (!files?.length || !jobId) return;
      setActionError(null);
      try {
        const fd = new FormData();
        Array.from(files).forEach((f) => fd.append("files", f));
        await api.upload(`/playground/jobs/${jobId}/upload`, fd);
        await refetch();
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Ошибка загрузки");
      }
    },
    [jobId, refetch]
  );

  const promote = async (fileId: number) => {
    setActionHint(null);
    try {
      const res = await api.post<{ message: string }>(`/playground/files/${fileId}/promote-to-calls`);
      setActionError(null);
      setActionHint(res.message || "Сохранено в общую базу звонков");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Ошибка сохранения");
    }
  };

  const selectFile = (f: PlaygroundFile) => {
    setSelectedFileId(f.id);
    setSelected(f);
  };

  return (
    <>
      <h1 className="page-title">Плейграунд</h1>
      <div className="playground-layout">
        <div className="card playground-setup">
          <h3>Загрузка и настройка</h3>
          <div className="playground-setup-row">
            <div className="form-group">
              <label>Сценарий оценки</label>
              <select value={scenarioId} onChange={(e) => setScenarioId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">— выберите —</option>
                {scenarios?.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <label className="playground-setup-checkbox">
              <input type="checkbox" checked={useScenarioPrompt} onChange={(e) => setUseScenarioPrompt(e.target.checked)} />
              Использовать промпт из сценария
            </label>
          </div>
          {!useScenarioPrompt && (
            <div className="form-group">
              <label>Тестовый промпт</label>
              <textarea value={customPrompt} onChange={(e) => setCustomPrompt(e.target.value)} rows={4} />
            </div>
          )}
          {!jobId ? (
            <button type="button" className="btn btn-primary" onClick={() => createJob.mutate()} disabled={createJob.isPending}>
              Создать сессию
            </button>
          ) : (
            <>
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); onDrop(e.dataTransfer.files); }}
                style={{ border: "2px dashed var(--border)", borderRadius: 10, padding: "2rem", textAlign: "center", marginBottom: "1rem" }}
              >
                Перетащите .mp3 / .wav
                <br />
                <input type="file" multiple accept=".mp3,.wav" style={{ marginTop: "1rem" }} onChange={(e) => onDrop(e.target.files)} />
              </div>
              <div className="playground-setup-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => runAnalysis.mutate()}
                  disabled={!canRun}
                >
                  {runAnalysis.isPending || isProcessing(job) ? "Обработка…" : "Запустить анализ"}
                </button>
                {jobId && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      clearSession();
                      setSelected(null);
                      setActionError(null);
                    }}
                  >
                    Новая сессия
                  </button>
                )}
              </div>
              {!canRun && job && job.files.length > 0 && !isProcessing(job) && (
                <p style={{ fontSize: "0.85rem", color: "var(--muted)", marginTop: "0.5rem" }}>
                  Все файлы уже обработаны. Загрузите новый файл или дождитесь завершения текущего анализа.
                </p>
              )}
              {isProcessing(job) && (
                <p style={{ fontSize: "0.85rem", color: "var(--primary)", marginTop: "0.5rem" }}>
                  Идёт распознавание и анализ — первая загрузка модели ASR может занять 3–5 минут.
                </p>
              )}
              {job && job.files.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <div style={{ height: 8, background: "var(--surface2)", borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ width: `${progress}%`, height: "100%", background: "var(--primary)", transition: "width 0.3s" }} />
                  </div>
                  <p style={{ fontSize: "0.8rem", color: "var(--muted)", marginTop: "0.35rem" }}>{progress}% завершено</p>
                </div>
              )}
            </>
          )}
          {actionError && (
            <p style={{ color: "var(--red)", fontSize: "0.85rem", marginTop: "0.75rem" }}>{actionError}</p>
          )}
          {actionHint && (
            <p style={{ color: "var(--primary)", fontSize: "0.85rem", marginTop: "0.75rem" }}>{actionHint}</p>
          )}
        </div>

        <div className="card playground-results">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
              marginBottom: "0.75rem",
            }}
          >
            <h3 style={{ margin: 0 }}>Результаты</h3>
            {job && readyFilesCount > 0 && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => promoteAll.mutate()}
                disabled={promoteAll.isPending || isProcessing(job)}
                title="Сохранить все успешно проанализированные файлы сессии"
              >
                {promoteAll.isPending
                  ? "Сохранение…"
                  : `Сохранить все в базу (${readyFilesCount})`}
              </button>
            )}
          </div>
          {!job ? (
            <p className="empty">Создайте сессию и загрузите файлы</p>
          ) : (
            <ul style={{ listStyle: "none" }}>
              {job.files.map((f) => (
                <li
                  key={f.id}
                  style={{ padding: "0.75rem", borderBottom: "1px solid var(--border)", cursor: "pointer", background: selected?.id === f.id ? "var(--surface2)" : undefined }}
                  onClick={() => selectFile(f)}
                >
                  {f.filename} — <span className="badge badge-gray">{STATUS_LABEL[f.status] || f.status}</span>
                  {f.error_message && (
                    <span style={{ display: "block", fontSize: "0.75rem", color: "var(--red)", marginTop: "0.25rem" }}>
                      {f.error_message}
                    </span>
                  )}
                  {f.analysis?.total_score != null && <> <ScoreBadge score={f.analysis.total_score} /></>}
                </li>
              ))}
            </ul>
          )}
          {actionHint && (
            <p style={{ color: "var(--primary)", fontSize: "0.85rem", marginTop: "0.75rem" }}>{actionHint}</p>
          )}
        </div>
      </div>

      {selected?.status === "ready" && (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h3>Детали: {selected.filename}</h3>
          <div className="grid-3" style={{ marginTop: "1rem" }}>
            <div>
              {selected.analysis && (
                <>
                  <p className={`score-big ${selected.analysis.total_score && selected.analysis.total_score >= 80 ? "green" : "yellow"}`}>
                    {selected.analysis.total_score}/100
                  </p>
                  <p>{selected.analysis.summary}</p>
                  <p><strong>Боли:</strong> {selected.analysis.client_pains}</p>
                  <p><strong>Итог:</strong> {selected.analysis.call_outcome}</p>
                </>
              )}
              <button type="button" className="btn btn-primary" style={{ marginTop: "1rem" }} onClick={() => promote(selected.id)}>
                Сохранить в общую базу звонков
              </button>
            </div>
            <div>
              <AudioWaveform
                audioUrl={selected.audio_url ?? null}
                utterances={sortUtterances(selected.transcription?.utterances)}
                onRegisterSeek={(seek) => {
                  seekRef.current = seek;
                }}
              />
              <div style={{ maxHeight: 300, overflowY: "auto", marginTop: "0.75rem" }}>
                <TranscriptList
                  utterances={selected.transcription?.utterances}
                  fullText={selected.transcription?.full_text}
                  onSeek={(t) => seekRef.current(t)}
                />
              </div>
            </div>
            <div>
              <h4>Чек-лист</h4>
              <CriteriaChecklist criteria={selected.analysis?.criteria_results} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
