import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
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
  const [setupOpen, setSetupOpen] = useState(() => !!jobId);

  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });

  const { data: job, refetch } = useQuery({
    queryKey: ["playground", jobId],
    queryFn: () => api.get<Job>(`/playground/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => (isProcessing(q.state.data) ? 15000 : false),
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
    const match = selectedFileId ? job.files.find((f) => f.id === selectedFileId) : undefined;
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

  useEffect(() => {
    if (jobId) setSetupOpen(true);
  }, [jobId]);

  const createJob = useMutation({
    mutationFn: () =>
      api.post<Job>("/playground/jobs", {
        scenario_id: scenarioId || null,
        use_scenario_prompt: useScenarioPrompt,
        custom_prompt: useScenarioPrompt ? null : customPrompt,
      }),
    onSuccess: (j) => {
      setJobId(j.id);
      setSetupOpen(true);
      setActionError(null);
    },
    onError: (e: Error) => setActionError(e.message),
  });

  const resetToStart = () => {
    clearSession();
    setSelected(null);
    setActionError(null);
    setActionHint(null);
    setSetupOpen(false);
  };

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
      <div className="page-header">
        <h1 className="page-title">Плейграунд</h1>
        <div className="page-header__actions">
          {!jobId && !setupOpen && (
            <button type="button" className="btn btn-primary" onClick={() => setSetupOpen(true)}>
              <Plus size={16} /> Создать сессию
            </button>
          )}
          {!jobId && setupOpen && (
            <button type="button" className="btn btn-secondary" onClick={() => setSetupOpen(false)}>
              Отмена
            </button>
          )}
          {jobId && (
            <button type="button" className="btn btn-secondary" onClick={resetToStart}>
              Новая сессия
            </button>
          )}
        </div>
      </div>

      <div className="playground-layout">
        {!setupOpen && !jobId && (
          <div className="card">
            <p className="empty">Создайте сессию, чтобы выбрать сценарий и загрузить файлы для анализа</p>
          </div>
        )}

        {setupOpen && (
          <div className="card playground-setup">
            <h3>{jobId ? "Загрузка и настройка" : "Новая сессия"}</h3>
            <div className="playground-setup-row">
              <div className="form-group">
                <label>Сценарий оценки</label>
                <select
                  value={scenarioId}
                  onChange={(e) => setScenarioId(e.target.value ? Number(e.target.value) : "")}
                  disabled={!!jobId}
                >
                  <option value="">— выберите —</option>
                  {scenarios?.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              <label className="checkbox-row playground-setup-checkbox">
                <input
                  type="checkbox"
                  checked={useScenarioPrompt}
                  onChange={(e) => setUseScenarioPrompt(e.target.checked)}
                  disabled={!!jobId}
                />
                Использовать промпт из сценария
              </label>
            </div>
            {!useScenarioPrompt && (
              <div className="form-group">
                <label>Тестовый промпт</label>
                <textarea
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  rows={4}
                  disabled={!!jobId}
                />
              </div>
            )}
            {!jobId ? (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => createJob.mutate()}
                disabled={createJob.isPending}
              >
                {createJob.isPending ? "Создание…" : "Начать"}
              </button>
            ) : (
              <>
                <div
                  className="dropzone"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { e.preventDefault(); onDrop(e.dataTransfer.files); }}
                >
                  Перетащите .mp3 / .wav
                  <br />
                  <input type="file" multiple accept=".mp3,.wav" onChange={(e) => onDrop(e.target.files)} />
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
                </div>
                {!canRun && job && job.files.length > 0 && !isProcessing(job) && (
                  <p className="text-hint">Все файлы уже обработаны. Загрузите новый файл или дождитесь завершения текущего анализа.</p>
                )}
                {isProcessing(job) && (
                  <p className="text-hint">Идёт распознавание и анализ — первая загрузка модели ASR может занять 3–5 минут.</p>
                )}
                {job && job.files.length > 0 && (
                  <div className="progress">
                    <div className="progress__track">
                      <div className="progress__fill" style={{ width: `${progress}%` }} />
                    </div>
                    <p className="progress__label">{progress}% завершено</p>
                  </div>
                )}
              </>
            )}
            {actionError && <p className="text-error">{actionError}</p>}
            {actionHint && <p className="text-success">{actionHint}</p>}
          </div>
        )}

        {jobId && (
          <div className="card playground-results">
            <div className="card-header">
              <h3>Результаты</h3>
              {readyFilesCount > 0 && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => promoteAll.mutate()}
                  disabled={promoteAll.isPending || isProcessing(job)}
                  title="Сохранить все успешно проанализированные файлы сессии"
                >
                  {promoteAll.isPending ? "Сохранение…" : `Сохранить все в базу (${readyFilesCount})`}
                </button>
              )}
            </div>
            {!job?.files.length ? (
              <p className="empty">Загрузите файлы выше</p>
            ) : (
              <ul className="list-plain">
                {job.files.map((f) => (
                  <li
                    key={f.id}
                    className={`list-item${selected?.id === f.id ? " list-item--active" : ""}`}
                    onClick={() => selectFile(f)}
                  >
                    {f.filename} — <span className="badge badge-gray">{STATUS_LABEL[f.status] || f.status}</span>
                    {f.error_message && <span className="list-item__error">{f.error_message}</span>}
                    {f.analysis?.total_score != null && <> <ScoreBadge score={f.analysis.total_score} /></>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {selected?.status === "ready" && (
        <div className="card playground-detail">
          <h3>Детали: {selected.filename}</h3>
          <div className="grid-3">
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
              <button type="button" className="btn btn-primary" style={{ marginTop: "var(--space-4)" }} onClick={() => promote(selected.id)}>
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
              <div className="scroll-panel scroll-panel--sm">
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
