import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import { api } from "../api/client";

type Criterion = {
  /** Stable id for React / dnd-kit — must not change when editing `key` */
  clientId: string;
  key: string;
  name: string;
  weight_percent: number;
  max_score: number;
  prompt: string;
  sort_order: number;
};

type ApiCriterion = Omit<Criterion, "clientId"> & { id: number };

function newClientId(): string {
  return `c-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function criterionFromApi(c: ApiCriterion): Criterion {
  return {
    clientId: `criterion-${c.id}`,
    key: c.key,
    name: c.name,
    weight_percent: c.weight_percent,
    max_score: c.max_score,
    prompt: c.prompt,
    sort_order: c.sort_order,
  };
}

function criteriaForApi(list: Criterion[]): Omit<Criterion, "clientId">[] {
  return list.map(({ clientId: _clientId, ...c }, i) => ({ ...c, sort_order: i }));
}

type Scenario = {
  id: number;
  name: string;
  system_prompt: string;
  llm_model: string;
  is_active: boolean;
  criteria: ApiCriterion[];
};

const ASR_MODELS = [
  "OvozifyLabs/whisper-small-uz-v1",
  "Jonibek21/Zehnova-Uzbek-STT",
  "zafarrr/uzbek-stt-fastconformer-v1.2",
];

const LLM_MODELS = ["gpt-4o-mini", "gpt-4o", "gemini-1.5-flash", "qwen3.5:4b"];

const emptyCriterion = (): Criterion => ({
  clientId: newClientId(),
  key: "",
  name: "",
  weight_percent: 10,
  max_score: 10,
  prompt: "",
  sort_order: 0,
});

/** Avoids type="number" quirks: empty field while typing, no leading zeros. */
function IntegerInput({
  value,
  onChange,
  min = 0,
}: {
  value: number;
  onChange: (n: number) => void;
  min?: number;
}) {
  const [text, setText] = useState(String(value));
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setText(String(value));
  }, [value]);

  const commit = (raw: string) => {
    if (raw === "") {
      setText("");
      return;
    }
    if (!/^\d+$/.test(raw)) return;
    const n = Math.max(min, parseInt(raw, 10));
    setText(String(n));
    onChange(n);
  };

  return (
    <input
      type="text"
      inputMode="numeric"
      value={text}
      onFocus={() => {
        focused.current = true;
      }}
      onBlur={() => {
        focused.current = false;
        if (text === "") {
          setText(String(min));
          onChange(min);
        } else {
          commit(text);
        }
      }}
      onChange={(e) => commit(e.target.value)}
    />
  );
}

function SortableCriterion({
  c,
  index,
  onChange,
  onRemove,
}: {
  c: Criterion;
  index: number;
  onChange: (i: number, c: Criterion) => void;
  onRemove: (i: number) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: c.clientId });
  const style = { transform: CSS.Transform.toString(transform), transition };

  return (
    <div ref={setNodeRef} className="card criterion-card" style={style}>
      <div className="criterion-card__header">
        <button type="button" className="btn btn-secondary btn-icon" {...attributes} {...listeners} aria-label="Drag">
          <GripVertical size={18} />
        </button>
        <strong>Критерий {index + 1}</strong>
        <button type="button" className="btn btn-danger btn-sm" onClick={() => onRemove(index)}>
          Удалить
        </button>
      </div>
      <div className="grid-2">
        <div className="form-group">
          <label>Ключ</label>
          <input value={c.key} onChange={(e) => onChange(index, { ...c, key: e.target.value })} />
        </div>
        <div className="form-group">
          <label>Название</label>
          <input value={c.name} onChange={(e) => onChange(index, { ...c, name: e.target.value })} />
        </div>
        <div className="form-group">
          <label>Вес %</label>
          <IntegerInput
            value={c.weight_percent}
            onChange={(weight_percent) => onChange(index, { ...c, weight_percent })}
          />
        </div>
        <div className="form-group">
          <label>Макс. балл</label>
          <IntegerInput
            value={c.max_score}
            onChange={(max_score) => onChange(index, { ...c, max_score })}
          />
        </div>
      </div>
      <div className="form-group">
        <label>Промпт критерия</label>
        <textarea value={c.prompt} onChange={(e) => onChange(index, { ...c, prompt: e.target.value })} rows={3} />
      </div>
    </div>
  );
}

export default function ScenarioEditPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = id === "new";

  const { data } = useQuery({
    queryKey: ["scenario", id],
    queryFn: () => api.get<Scenario>(`/scenarios/${id}`),
    enabled: !isNew && !!id,
  });

  const [name, setName] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [llmModel, setLlmModel] = useState("gpt-4o-mini");
  const [isActive, setIsActive] = useState(true);
  const [criteria, setCriteria] = useState<Criterion[]>([emptyCriterion()]);
  const [dirty, setDirty] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  useEffect(() => {
    if (data) {
      setName(data.name);
      setSystemPrompt(data.system_prompt);
      setLlmModel(data.llm_model);
      setIsActive(data.is_active);
      setCriteria(
        data.criteria.length ? data.criteria.map(criterionFromApi) : [emptyCriterion()]
      );
    }
  }, [data]);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        system_prompt: systemPrompt,
        llm_model: llmModel,
        is_active: isActive,
        criteria: criteriaForApi(criteria),
      };
      if (isNew) return api.post<Scenario>("/scenarios", body);
      return api.put<Scenario>(`/scenarios/${id}`, body);
    },
    onSuccess: (s) => {
      setDirty(false);
      setSaveError(null);
      navigate(`/scenarios/${s.id}`);
    },
    onError: (e: Error) => setSaveError(e.message || "Не удалось сохранить сценарий"),
  });

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = criteria.findIndex((c) => c.clientId === active.id);
    const newIndex = criteria.findIndex((c) => c.clientId === over.id);
    setCriteria(arrayMove(criteria, oldIndex, newIndex).map((c, i) => ({ ...c, sort_order: i })));
    setDirty(true);
  };

  return (
    <>
      <h1 className="page-title">{isNew ? "Новый сценарий" : `Сценарий: ${name}`}</h1>
      <div className="card scenario-editor">
        <div className="form-group">
          <label>Название</label>
          <input value={name} onChange={(e) => { setName(e.target.value); setDirty(true); }} />
        </div>
        <div className="form-group">
          <label>Модель LLM</label>
          <select value={llmModel} onChange={(e) => { setLlmModel(e.target.value); setDirty(true); }}>
            {LLM_MODELS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
        <label className="checkbox-row" style={{ marginBottom: "var(--space-4)" }}>
          <input type="checkbox" checked={isActive} onChange={(e) => { setIsActive(e.target.checked); setDirty(true); }} />
          Активен
        </label>
        <div className="form-group">
          <label>Системный промпт</label>
          <textarea value={systemPrompt} onChange={(e) => { setSystemPrompt(e.target.value); setDirty(true); }} rows={5} placeholder="Ты валидатор качества работы службы поддержки..." />
        </div>
        <h3 className="form-section-title">Критерии (перетаскивайте за ⋮⋮)</h3>
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={criteria.map((c) => c.clientId)} strategy={verticalListSortingStrategy}>
            {criteria.map((c, i) => (
              <SortableCriterion
                key={c.clientId}
                c={c}
                index={i}
                onChange={(idx, nc) => {
                  const n = [...criteria];
                  n[idx] = nc;
                  setCriteria(n);
                  setDirty(true);
                }}
                onRemove={(idx) => {
                  setCriteria(criteria.filter((_, j) => j !== idx));
                  setDirty(true);
                }}
              />
            ))}
          </SortableContext>
        </DndContext>
        <button type="button" className="btn btn-secondary" onClick={() => { setCriteria([...criteria, emptyCriterion()]); setDirty(true); }}>
          + Критерий
        </button>
      </div>
      {dirty && (
        <div className="sticky-bar">
          <button type="button" className="btn btn-secondary" onClick={() => navigate("/scenarios")}>Отменить</button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setSaveError(null);
              save.mutate();
            }}
            disabled={save.isPending}
          >
            Сохранить изменения
          </button>
          {saveError && <p className="text-error">{saveError}</p>}
        </div>
      )}
    </>
  );
}
