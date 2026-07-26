import { useState } from "react";

export type CriterionResult = {
  score: number;
  passed: boolean;
  comment: string;
  status?: string;
};

const CRITERION_LABELS: Record<string, string> = {
  greeting: "Приветствие",
  politeness: "Вежливость",
  need_discovery: "Выявление потребности",
  solution_proposal: "Предложение решения",
  closing: "Завершение",
};

function criterionLabel(key: string): string {
  return CRITERION_LABELS[key] ?? key.replace(/_/g, " ");
}

function parseCriterion(value: unknown): CriterionResult | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const o = value as Record<string, unknown>;
  if (typeof o.score !== "number" || typeof o.passed !== "boolean") return null;
  return {
    score: o.score,
    passed: o.passed,
    comment: typeof o.comment === "string" ? o.comment : "",
    status: typeof o.status === "string" ? o.status : undefined,
  };
}

function CriterionIcon({ passed, status }: { passed: boolean; status?: string }) {
  if (status === "not_applicable") {
    return (
      <span className="criteria-checklist__icon criteria-checklist__icon--na" title="Не применимо">
        —
      </span>
    );
  }
  return (
    <span
      className={`criteria-checklist__icon ${passed ? "criteria-checklist__icon--ok" : "criteria-checklist__icon--fail"}`}
      aria-hidden
    >
      {passed ? "✓" : "✗"}
    </span>
  );
}

function CriterionRow({ itemKey, raw }: { itemKey: string; raw: unknown }) {
  const [open, setOpen] = useState(false);
  const c = parseCriterion(raw);

  if (!c) {
    return (
      <li className="criteria-checklist__item criteria-checklist__item--invalid">
        <span className="criteria-checklist__name">{criterionLabel(itemKey)}</span>
        <span className="criteria-checklist__comment">{String(raw)}</span>
      </li>
    );
  }

  const hasComment = Boolean(c.comment?.trim());

  return (
    <li
      className={`criteria-checklist__item ${c.passed ? "criteria-checklist__item--passed" : "criteria-checklist__item--failed"}`}
    >
      <CriterionIcon passed={c.passed} status={c.status} />
      <div className="criteria-checklist__body">
        <div className="criteria-checklist__head">
          <span className="criteria-checklist__name">{criterionLabel(itemKey)}</span>
          <span className="criteria-checklist__score">{c.score} б.</span>
        </div>
        {hasComment && (
          <>
            <button
              type="button"
              className="criteria-checklist__toggle"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? "Скрыть комментарий" : "Комментарий"}
            </button>
            {open && <p className="criteria-checklist__comment">{c.comment}</p>}
          </>
        )}
      </div>
    </li>
  );
}

type Props = {
  criteria?: Record<string, unknown> | null;
  emptyMessage?: string;
};

export default function CriteriaChecklist({ criteria, emptyMessage = "Нет данных чек-листа" }: Props) {
  if (!criteria || Object.keys(criteria).length === 0) {
    return <p className="criteria-checklist__empty">{emptyMessage}</p>;
  }

  return (
    <ul className="criteria-checklist">
      {Object.entries(criteria).map(([key, raw]) => (
        <CriterionRow key={key} itemKey={key} raw={raw} />
      ))}
    </ul>
  );
}
