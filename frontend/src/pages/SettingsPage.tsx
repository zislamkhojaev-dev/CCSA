import { useEffect, useState } from "react";
import { Routes, Route, NavLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const WEEKDAYS = [
  { v: 0, l: "Пн" },
  { v: 1, l: "Вт" },
  { v: 2, l: "Ср" },
  { v: 3, l: "Чт" },
  { v: 4, l: "Пт" },
  { v: 5, l: "Сб" },
  { v: 6, l: "Вс" },
];

const ASR_MODELS = [
  "OvozifyLabs/whisper-small-uz-v1",
  "Jonibek21/Zehnova-Uzbek-STT",
  "zafarrr/uzbek-stt-fastconformer-v1.2",
];

const DIARIZATION_METHODS = [
  { value: "stereo_channels", label: "Стерео-каналы (левый=клиент, правый=оператор)" },
  { value: "pyannote", label: "Pyannote (1× ASR, по голосу)" },
  { value: "mono", label: "Моно без диаризации" },
];

function StickySave({ dirty, onSave, onCancel }: { dirty: boolean; onSave: () => void; onCancel?: () => void }) {
  if (!dirty) return null;
  return (
    <div className="sticky-bar">
      {onCancel && <button type="button" className="btn btn-secondary" onClick={onCancel}>Отменить</button>}
      <button type="button" className="btn btn-primary" onClick={onSave}>Сохранить изменения</button>
    </div>
  );
}

function ModelsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["settings-models"],
    queryFn: () =>
      api.get<{
        asr_provider: string;
        asr_model: string;
        asr_diarization_method: string;
        asr_api_url: string;
        llm_provider: string;
        llm_model: string;
        pii_anonymization: boolean;
        openai_api_key_set: boolean;
        gemini_api_key_set: boolean;
        ollama_base_url: string;
        asr_max_parallel: number;
        asr_http_timeout_sec: number;
        playground_sequential: boolean;
        celery_worker_concurrency: number;
      }>("/settings/models"),
  });
  const [form, setForm] = useState({
    asr_provider: "local",
    asr_model: ASR_MODELS[0],
    asr_diarization_method: "stereo_channels",
    asr_api_url: "",
    asr_max_parallel: 1,
    asr_http_timeout_sec: 600,
    playground_sequential: true,
    celery_worker_concurrency: 1,
    llm_provider: "openai",
    llm_model: "gpt-4o-mini",
    pii_anonymization: true,
    openai_api_key: "",
    gemini_api_key: "",
    ollama_base_url: "http://host.docker.internal:11434",
  });
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data) {
      setForm((f) => ({
        ...f,
        asr_provider: data.asr_provider,
        asr_model: data.asr_model,
        asr_diarization_method: data.asr_diarization_method || "stereo_channels",
        asr_api_url: data.asr_api_url,
        llm_provider: data.llm_provider,
        llm_model: data.llm_model,
        pii_anonymization: data.pii_anonymization,
        ollama_base_url: data.ollama_base_url,
        asr_max_parallel: data.asr_max_parallel ?? 1,
        asr_http_timeout_sec: data.asr_http_timeout_sec ?? 600,
        playground_sequential: data.playground_sequential ?? true,
        celery_worker_concurrency: data.celery_worker_concurrency ?? 1,
      }));
    }
  }, [data]);

  const save = useMutation({
    mutationFn: () => api.put("/settings/models", form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings-models"] });
      setDirty(false);
    },
  });

  return (
  <>
    <div className="card settings-tab-content">
      <h3>ASR (распознавание речи)</h3>
      <div className="form-group">
        <label>Провайдер</label>
        <select value={form.asr_provider} onChange={(e) => { setForm({ ...form, asr_provider: e.target.value }); setDirty(true); }}>
          <option value="local">Локальная (Faster-Whisper)</option>
          <option value="openai">OpenAI Whisper API</option>
          <option value="other">Другие API</option>
        </select>
      </div>
      <div className="form-group">
        <label>Модель</label>
        <select value={form.asr_model} onChange={(e) => { setForm({ ...form, asr_model: e.target.value }); setDirty(true); }}>
          {ASR_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      {form.asr_provider === "local" && (
        <div className="form-group">
          <label>Диаризация</label>
          <select
            value={form.asr_diarization_method}
            onChange={(e) => { setForm({ ...form, asr_diarization_method: e.target.value }); setDirty(true); }}
          >
            {DIARIZATION_METHODS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <p className="form-hint">
            Pyannote требует HF_TOKEN и лицензии на pyannote/speaker-diarization-3.1. Без токена — fallback на стерео-каналы или моно.
          </p>
        </div>
      )}
      <h4 className="form-section-title">Производительность ASR</h4>
      <div className="form-group">
        <label>Макс. параллельных запросов к STT</label>
        <input
          type="number"
          min={1}
          max={8}
          value={form.asr_max_parallel}
          onChange={(e) => {
            setForm({ ...form, asr_max_parallel: Math.max(1, Math.min(8, Number(e.target.value) || 1)) });
            setDirty(true);
          }}
        />
        <p className="form-hint">
          Сколько распознаваний одновременно (через Redis). На CPU рекомендуется 1.
        </p>
      </div>
      <div className="form-group">
        <label>Таймаут HTTP к STT (секунды)</label>
        <input
          type="number"
          min={60}
          max={7200}
          value={form.asr_http_timeout_sec}
          onChange={(e) => {
            setForm({ ...form, asr_http_timeout_sec: Math.max(60, Math.min(7200, Number(e.target.value) || 600)) });
            setDirty(true);
          }}
        />
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={form.playground_sequential}
          onChange={(e) => { setForm({ ...form, playground_sequential: e.target.checked }); setDirty(true); }}
        />
        Плейграунд: обрабатывать файлы по одному (рекомендуется)
      </label>
      <div className="form-group">
        <label>Параллельность Celery worker</label>
        <input
          type="number"
          min={1}
          max={8}
          value={form.celery_worker_concurrency}
          onChange={(e) => {
            setForm({ ...form, celery_worker_concurrency: Math.max(1, Math.min(8, Number(e.target.value) || 1)) });
            setDirty(true);
          }}
        />
        <p className="form-hint">
          Применяется после перезапуска: задайте в .env{" "}
          <code>CELERY_WORKER_CONCURRENCY=…</code> и выполните{" "}
          <code>docker compose restart celery-worker</code>.
        </p>
      </div>
      {form.asr_provider !== "local" && (
        <>
          <div className="form-group">
            <label>URL сервера ASR</label>
            <input value={form.asr_api_url} onChange={(e) => { setForm({ ...form, asr_api_url: e.target.value }); setDirty(true); }} />
          </div>
          <div className="form-group">
            <label>API ключ ASR</label>
            <input type="password" placeholder="••••" onChange={(e) => { setForm({ ...form, asr_api_key: e.target.value } as never); setDirty(true); }} />
          </div>
        </>
      )}
      <h3 className="form-section-title">LLM (аналитика)</h3>
      <div className="form-group">
        <label>Провайдер</label>
        <select value={form.llm_provider} onChange={(e) => { setForm({ ...form, llm_provider: e.target.value }); setDirty(true); }}>
          <option value="openai">OpenAI</option>
          <option value="gemini">Gemini</option>
          <option value="local">Local (Ollama)</option>
        </select>
      </div>
      <div className="form-group">
        <label>Модель</label>
        <input value={form.llm_model} onChange={(e) => { setForm({ ...form, llm_model: e.target.value }); setDirty(true); }} />
      </div>
      {form.llm_provider === "openai" && (
        <div className="form-group">
          <label>OpenAI API Key {data?.openai_api_key_set && "(установлен)"}</label>
          <input type="password" placeholder="sk-..." onChange={(e) => { setForm({ ...form, openai_api_key: e.target.value }); setDirty(true); }} />
        </div>
      )}
      {form.llm_provider === "gemini" && (
        <div className="form-group">
          <label>Gemini API Key {data?.gemini_api_key_set && "(установлен)"}</label>
          <input type="password" onChange={(e) => { setForm({ ...form, gemini_api_key: e.target.value }); setDirty(true); }} />
        </div>
      )}
      {form.llm_provider === "local" && (
        <div className="form-group">
          <label>Ollama URL</label>
          <input value={form.ollama_base_url} onChange={(e) => { setForm({ ...form, ollama_base_url: e.target.value }); setDirty(true); }} />
        </div>
      )}
      <label className="checkbox-row">
        <input type="checkbox" checked={form.pii_anonymization} onChange={(e) => { setForm({ ...form, pii_anonymization: e.target.checked }); setDirty(true); }} />
        Включить анонимизацию данных перед отправкой в облачные LLM ([PII_DATA])
      </label>
    </div>
    <StickySave dirty={dirty} onSave={() => save.mutate()} />
  </>
  );
}

function WebitelTab() {
  const qc = useQueryClient();
  const { data, refetch } = useQuery({
    queryKey: ["settings-webitel"],
    queryFn: () => api.get<{ api_url: string; sync_cron: string; sync_days: number[]; sync_time_from: string; sync_time_to: string }>("/settings/webitel"),
  });
  const { data: dbData, refetch: refetchDb } = useQuery({
    queryKey: ["settings-webitel-db"],
    queryFn: () => api.get<{ host: string; port: number; database: string; user: string }>("/settings/webitel/db"),
  });
  const [wt, setWt] = useState({ url: "", token: "", cron: "*/30 * * * *", days: [0, 1, 2, 3, 4] as number[], from: "09:00", to: "18:00", freq: "30min" });
  const [db, setDb] = useState({ host: "", port: 5432, database: "webitel", user: "", password: "" });
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data) setWt((a) => ({ ...a, url: data.api_url, cron: data.sync_cron, days: data.sync_days, from: data.sync_time_from, to: data.sync_time_to }));
  }, [data]);
  useEffect(() => {
    if (dbData) setDb((d) => ({ ...d, host: dbData.host, port: dbData.port, database: dbData.database, user: dbData.user }));
  }, [dbData]);

  const freqToCron = (f: string) => (f === "daily" ? "0 9 * * *" : "*/30 * * * *");

  const save = async () => {
    await api.put("/settings/webitel", {
      api_url: wt.url,
      access_token: wt.token || undefined,
      sync_cron: freqToCron(wt.freq),
      sync_days: wt.days,
      sync_time_from: wt.from,
      sync_time_to: wt.to,
    });
    await api.put("/settings/webitel/db", { ...db, password: db.password || undefined });
    refetch();
    refetchDb();
    setDirty(false);
  };

  const testApi = async () => {
    const r = await api.post<{ ok: boolean; message: string }>("/settings/webitel/test");
    alert(r.ok ? "Webitel API: OK" : r.message || "Ошибка");
  };
  const testDb = async () => {
    const r = await api.post<{ ok: boolean; message: string }>("/settings/webitel/db/test");
    alert(r.message);
  };

  return (
  <>
    <div className="grid-2 settings-tab-content">
      <div className="card">
        <h3>Webitel API</h3>
        <div className="form-group"><label>Хост / URL</label><input value={wt.url} onChange={(e) => { setWt({ ...wt, url: e.target.value }); setDirty(true); }} placeholder="https://webitel.example" /></div>
        <div className="form-group"><label>Access Token</label><input type="password" onChange={(e) => { setWt({ ...wt, token: e.target.value }); setDirty(true); }} /></div>
        <button type="button" className="btn btn-secondary" onClick={testApi}>Проверить соединение</button>
        <h4 className="subsection-title">Расписание синхронизации</h4>
        <div className="form-group">
          <label>Частота</label>
          <select value={wt.freq} onChange={(e) => { setWt({ ...wt, freq: e.target.value }); setDirty(true); }}>
            <option value="30min">Каждые 30 минут</option>
            <option value="daily">Раз в сутки (09:00)</option>
          </select>
        </div>
        <div className="checkbox-group">
          {WEEKDAYS.map((d) => (
            <label key={d.v} className="checkbox-row">
              <input type="checkbox" checked={wt.days.includes(d.v)} onChange={(e) => {
              setWt({ ...wt, days: e.target.checked ? [...wt.days, d.v] : wt.days.filter((x) => x !== d.v) });
              setDirty(true);
            }} /> {d.l}</label>
          ))}
        </div>
        <div className="grid-2">
          <div className="form-group"><label>С</label><input type="time" value={wt.from} onChange={(e) => { setWt({ ...wt, from: e.target.value }); setDirty(true); }} /></div>
          <div className="form-group"><label>По</label><input type="time" value={wt.to} onChange={(e) => { setWt({ ...wt, to: e.target.value }); setDirty(true); }} /></div>
        </div>
      </div>
      <div className="card">
        <h3>Webitel DB</h3>
        <div className="form-group"><label>Хост</label><input value={db.host} onChange={(e) => { setDb({ ...db, host: e.target.value }); setDirty(true); }} /></div>
        <div className="form-group"><label>Порт</label><input type="number" value={db.port} onChange={(e) => { setDb({ ...db, port: Number(e.target.value) }); setDirty(true); }} /></div>
        <div className="form-group"><label>База</label><input value={db.database} onChange={(e) => { setDb({ ...db, database: e.target.value }); setDirty(true); }} /></div>
        <div className="form-group"><label>Логин</label><input value={db.user} onChange={(e) => { setDb({ ...db, user: e.target.value }); setDirty(true); }} /></div>
        <div className="form-group"><label>Пароль</label><input type="password" onChange={(e) => { setDb({ ...db, password: e.target.value }); setDirty(true); }} /></div>
        <button type="button" className="btn btn-secondary" onClick={testDb}>Проверить соединение</button>
      </div>
    </div>
    <StickySave dirty={dirty} onSave={save} />
  </>
  );
}

type QualityData = {
  threshold_good: number;
  threshold_mid: number;
  target: number;
  topics: string[];
};

function QualityTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["settings-quality"],
    queryFn: () => api.get<QualityData>("/settings/quality"),
  });
  const [form, setForm] = useState<QualityData>({
    threshold_good: 80,
    threshold_mid: 50,
    target: 85,
    topics: [],
  });
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data) setForm({
      threshold_good: data.threshold_good,
      threshold_mid: data.threshold_mid,
      target: data.target,
      topics: data.topics ?? [],
    });
  }, [data]);

  const save = useMutation({
    mutationFn: () =>
      api.put("/settings/quality", {
        ...form,
        topics: form.topics.map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings-quality"] });
      setDirty(false);
    },
  });

  const [backfillHint, setBackfillHint] = useState<string | null>(null);

  const backfillTopics = useMutation({
    mutationFn: () => api.post<{ message: string }>("/settings/quality/backfill-topics"),
    onSuccess: (r) => {
      setBackfillHint(
        `${r.message} Обновите страницу звонка через 1–2 минуты — темы появятся по мере обработки.`,
      );
    },
    onError: (e: Error) => setBackfillHint(`Ошибка: ${e.message}`),
  });

  const [recoverHint, setRecoverHint] = useState<string | null>(null);

  const recoverStuck = useMutation({
    mutationFn: () => api.post<{ message: string }>("/settings/maintenance/recover-stuck-calls"),
    onSuccess: (r) => {
      setRecoverHint(`${r.message} Звонки вернутся в очередь и будут обработаны в течение 5 минут.`);
    },
    onError: (e: Error) => setRecoverHint(`Ошибка: ${e.message}`),
  });

  const setNum = (key: "threshold_good" | "threshold_mid" | "target", raw: string) => {
    const v = Math.max(0, Math.min(100, Number(raw) || 0));
    setForm((f) => ({ ...f, [key]: v }));
    setDirty(true);
  };

  const updateTopic = (idx: number, value: string) => {
    setForm((f) => ({ ...f, topics: f.topics.map((t, i) => (i === idx ? value : t)) }));
    setDirty(true);
  };
  const removeTopic = (idx: number) => {
    setForm((f) => ({ ...f, topics: f.topics.filter((_, i) => i !== idx) }));
    setDirty(true);
  };
  const addTopic = () => {
    setForm((f) => ({ ...f, topics: [...f.topics, ""] }));
    setDirty(true);
  };

  return (
  <>
    <div className="card settings-tab-content">
      <h3>Пороги качества</h3>
      <p className="text-muted">Определяют цвета и группировку оценок на дашбордах.</p>
      <div className="grid-2">
        <div className="form-group">
          <label>Порог «хорошо» (зелёный), %</label>
          <input type="number" min={0} max={100} value={form.threshold_good} onChange={(e) => setNum("threshold_good", e.target.value)} />
        </div>
        <div className="form-group">
          <label>Порог «средне» (жёлтый), %</label>
          <input type="number" min={0} max={100} value={form.threshold_mid} onChange={(e) => setNum("threshold_mid", e.target.value)} />
          <p className="form-hint">Ниже этого порога — красный. Не может превышать порог «хорошо».</p>
        </div>
      </div>
      <div className="form-group">
        <label>Целевой средний балл (target), %</label>
        <input type="number" min={0} max={100} value={form.target} onChange={(e) => setNum("target", e.target.value)} />
        <p className="form-hint">Отображается целевой линией на графике динамики среднего балла.</p>
      </div>

      <h3 className="form-section-title">Таксономия тем звонков</h3>
      <p className="text-muted">Список категорий, из которых LLM выбирает тему звонка. Держите его коротким и понятным.</p>
      <div className="topic-list">
        {form.topics.map((t, i) => (
          <div key={i} className="topic-row">
            <input
              className="form-input"
              value={t}
              placeholder="Название темы"
              onChange={(e) => updateTopic(i, e.target.value)}
            />
            <button type="button" className="btn btn-secondary" onClick={() => removeTopic(i)}>Удалить</button>
          </div>
        ))}
      </div>
      <button type="button" className="btn btn-secondary mt-2" onClick={addTopic}>+ Добавить тему</button>

      <h4 className="form-section-title">Классификация существующих звонков</h4>
      <p className="text-muted">
        Проставить тему звонкам без классификации или с «Не классифицировано» (например, если OpenAI был недоступен).
        Используется провайдер из вкладки «Модели и AI» — OpenAI, Gemini или Ollama.
      </p>
      <button
        type="button"
        className="btn btn-secondary"
        onClick={() => backfillTopics.mutate()}
        disabled={backfillTopics.isPending}
      >
        {backfillTopics.isPending ? "Запуск…" : "Классифицировать без темы"}
      </button>
      {backfillHint && (
        <p className={`form-hint mt-2 ${backfillHint.startsWith("Ошибка:") ? "text-error" : ""}`} role="status">
          {backfillHint}
        </p>
      )}

      <h4 className="form-section-title">Зависшие обработки</h4>
      <p className="text-muted">
        Если звонок надолго остался в статусе «Транскрибация» или «Анализ» (например, после
        перезапуска worker), вернуть его в очередь. Звонки, которые обрабатываются прямо сейчас,
        не затрагиваются.
      </p>
      <button
        type="button"
        className="btn btn-secondary"
        onClick={() => recoverStuck.mutate()}
        disabled={recoverStuck.isPending}
      >
        {recoverStuck.isPending ? "Запуск…" : "Восстановить зависшие звонки"}
      </button>
      {recoverHint && (
        <p className={`form-hint mt-2 ${recoverHint.startsWith("Ошибка:") ? "text-error" : ""}`} role="status">
          {recoverHint}
        </p>
      )}
    </div>
    <StickySave dirty={dirty} onSave={() => save.mutate()} />
  </>
  );
}

function AutomationTab() {
  const { data, refetch } = useQuery({
    queryKey: ["automation"],
    queryFn: () => api.get<{ batch_size: number; active_days: number[]; time_from: string; time_to: string; is_enabled: boolean }>("/settings/automation"),
  });
  const [batch, setBatch] = useState(10);
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [from, setFrom] = useState("09:00");
  const [to, setTo] = useState("18:00");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data) {
      setBatch(data.batch_size);
      setDays(data.active_days || []);
      setFrom(data.time_from || "09:00");
      setTo(data.time_to || "18:00");
    }
  }, [data]);

  const save = async () => {
    await api.put("/settings/automation", { batch_size: batch, active_days: days, time_from: from, time_to: to, is_enabled: true });
    refetch();
    setDirty(false);
  };

  return (
  <>
    <div className="card settings-tab-content">
      <h3>Автоматизация оценки</h3>
      <p className="text-muted">Автоматический скоринг поступающих звонков в заданном окне.</p>
      <div className="form-group">
        <label>Размер батча</label>
        <input type="number" min={1} max={100} value={batch} onChange={(e) => { setBatch(Number(e.target.value)); setDirty(true); }} />
      </div>
      <div className="checkbox-group">
        {WEEKDAYS.map((d) => (
          <label key={d.v} className="checkbox-row">
            <input type="checkbox" checked={days.includes(d.v)} onChange={(e) => {
            setDays(e.target.checked ? [...days, d.v] : days.filter((x) => x !== d.v));
            setDirty(true);
          }} /> {d.l}</label>
        ))}
      </div>
      <div className="grid-2">
        <div className="form-group"><label>Активность с</label><input type="time" value={from} onChange={(e) => { setFrom(e.target.value); setDirty(true); }} /></div>
        <div className="form-group"><label>до</label><input type="time" value={to} onChange={(e) => { setTo(e.target.value); setDirty(true); }} /></div>
      </div>
    </div>
    <StickySave dirty={dirty} onSave={save} />
  </>
  );
}

function AdminTab() {
  const { data, refetch } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<{ id: number; login: string; full_name: string; role: string; is_active: boolean; created_at: string }[]>("/settings/users"),
  });
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editPassword, setEditPassword] = useState("");

  const add = async () => {
    await api.post("/settings/users", { login, password, full_name: fullName, role: "supervisor" });
    setLogin(""); setPassword(""); setFullName("");
    refetch();
  };

  const resetPassword = async (id: number) => {
    if (!editPassword) return;
    await api.patch(`/settings/users/${id}`, { password: editPassword });
    setEditId(null);
    setEditPassword("");
    alert("Пароль обновлён");
  };

  return (
    <div className="card">
      <h3>Администрирование</h3>
      <table>
        <thead>
          <tr><th>Имя</th><th>Логин</th><th>Роль</th><th>Статус</th><th>Создан</th><th>Действия</th></tr>
        </thead>
        <tbody>
          {data?.map((u) => (
            <tr key={u.id}>
              <td>{u.full_name}</td>
              <td>{u.login}</td>
              <td>{u.role}</td>
              <td><span className={`badge ${u.is_active ? "badge-green" : "badge-gray"}`}>{u.is_active ? "Active" : "Inactive"}</span></td>
              <td>{new Date(u.created_at).toLocaleDateString("ru")}</td>
              <td>
                {editId === u.id ? (
                  <>
                    <input type="password" className="form-input" placeholder="Новый пароль" value={editPassword} onChange={(e) => setEditPassword(e.target.value)} style={{ width: 120 }} />
                    <button type="button" className="btn btn-primary" onClick={() => resetPassword(u.id)}>OK</button>
                  </>
                ) : (
                  <button type="button" className="btn btn-secondary" onClick={() => setEditId(u.id)}>Сбросить пароль</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h4 className="subsection-title">Добавить супервизора</h4>
      <div className="grid-2">
        <input className="form-input" placeholder="Логин" value={login} onChange={(e) => setLogin(e.target.value)} />
        <input className="form-input" placeholder="Имя" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        <input className="form-input" type="password" placeholder="Пароль" value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
      <button type="button" className="btn btn-primary" style={{ marginTop: "var(--space-4)" }} onClick={add}>Добавить</button>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <>
      <h1 className="page-title">Настройки</h1>
      <div className="tabs" role="tablist" aria-label="Разделы настроек">
        <NavLink to="/settings" end className={({ isActive }) => (isActive ? "active" : undefined)}>Модели и AI</NavLink>
        <NavLink to="/settings/webitel" className={({ isActive }) => (isActive ? "active" : undefined)}>Коннекторы</NavLink>
        <NavLink to="/settings/quality" className={({ isActive }) => (isActive ? "active" : undefined)}>Качество</NavLink>
        <NavLink to="/settings/automation" className={({ isActive }) => (isActive ? "active" : undefined)}>Автоматизация</NavLink>
        <NavLink to="/settings/admin" className={({ isActive }) => (isActive ? "active" : undefined)}>Администрирование</NavLink>
      </div>
      <Routes>
        <Route index element={<ModelsTab />} />
        <Route path="webitel" element={<WebitelTab />} />
        <Route path="quality" element={<QualityTab />} />
        <Route path="automation" element={<AutomationTab />} />
        <Route path="admin" element={<AdminTab />} />
      </Routes>
    </>
  );
}
