"""Build downloadable exports for research studies."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def _format_filters(filters: dict | None) -> str:
    if not filters:
        return "все звонки"
    parts: list[str] = []
    if filters.get("date_from"):
        parts.append(f"от {filters['date_from']}")
    if filters.get("date_to"):
        parts.append(f"до {filters['date_to']}")
    direction = filters.get("direction")
    if direction == "inbound":
        parts.append("входящие")
    elif direction == "outbound":
        parts.append("исходящие")
    if filters.get("operator_id"):
        parts.append(f"оператор #{filters['operator_id']}")
    if filters.get("queue"):
        parts.append(f"очередь «{filters['queue']}»")
    if filters.get("tag_id"):
        parts.append(f"тег #{filters['tag_id']}")
    elif filters.get("tag"):
        parts.append(f"тег «{filters['tag']}»")
    score_op = filters.get("score_op")
    score_value = filters.get("score_value")
    if score_op and score_value is not None:
        op = {"eq": "=", "lt": "<", "gt": ">"}.get(str(score_op), score_op)
        parts.append(f"оценка {op} {score_value}%")
    return ", ".join(parts) if parts else "все звонки"


def research_export_filename(study_id: int, title: str, *, ext: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    slug = re.sub(r"[\s_]+", "-", slug.strip())[:50] or "report"
    return f"research-{study_id}-{slug}.{ext}"


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


def build_research_markdown_export(study: Any) -> str:
    filters = study.filters_json if isinstance(study.filters_json, dict) else {}
    call_ids = study.call_ids if isinstance(study.call_ids, list) else []
    author = study.user.full_name if study.user else "—"

    lines = [
        f"# {study.title}",
        "",
        "## Параметры",
        "",
        f"- **Автор:** {author}",
        f"- **Создано:** {_fmt_dt(study.created_at)}",
        f"- **Завершено:** {_fmt_dt(study.finished_at)}",
        f"- **Фильтры:** {_format_filters(filters)}",
        f"- **Звонков в выборке:** {study.call_count or len(call_ids) or '—'}",
    ]
    if study.llm_model:
        lines.append(f"- **Модель LLM:** {study.llm_model}")
    if call_ids:
        ids_preview = ", ".join(f"#{i}" for i in call_ids[:30])
        if len(call_ids) > 30:
            ids_preview += f", … (+{len(call_ids) - 30})"
        lines.append(f"- **ID звонков:** {ids_preview}")

    lines.extend(
        [
            "",
            "## Промпт",
            "",
            study.prompt.strip(),
            "",
            "## Отчёт",
            "",
            (study.report_markdown or "").strip(),
            "",
        ]
    )
    return "\n".join(lines)


def build_research_json_export(study: Any) -> dict:
    filters = study.filters_json if isinstance(study.filters_json, dict) else {}
    call_ids = study.call_ids if isinstance(study.call_ids, list) else None
    return {
        "id": study.id,
        "title": study.title,
        "prompt": study.prompt,
        "filters": filters,
        "status": study.status,
        "call_count": study.call_count,
        "call_ids": call_ids,
        "llm_model": study.llm_model,
        "report_markdown": study.report_markdown,
        "error_message": study.error_message,
        "user_name": study.user.full_name if study.user else None,
        "created_at": study.created_at.isoformat() if study.created_at else None,
        "finished_at": study.finished_at.isoformat() if study.finished_at else None,
    }
