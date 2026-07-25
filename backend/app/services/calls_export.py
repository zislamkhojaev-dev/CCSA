"""Build rich call export rows (CSV / JSON) for sync and async jobs."""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisResult, Call, CallTag
from app.schemas.calls import CallExportFilters
from app.services.call_query import build_calls_count_query, build_calls_list_query

CALLS_EXPORT_MAX_ROWS = int(os.getenv("CALLS_EXPORT_MAX_ROWS", "5000"))
CALLS_EXPORT_SYNC_MAX_IDS = int(os.getenv("CALLS_EXPORT_SYNC_MAX_IDS", "1000"))

EXPORT_FIELDNAMES = [
    "id",
    "call_uuid",
    "operator_name",
    "direction",
    "duration",
    "client_number",
    "call_timestamp",
    "status",
    "total_score",
    "topic",
    "summary",
    "call_outcome",
    "tags",
]


def calls_export_filename(*, ext: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return f"calls-{stamp}.{ext}"


def parse_export_filters(filters: CallExportFilters | dict | None) -> dict[str, Any]:
    """Normalize filter payload into kwargs for build_calls_*_query."""
    if filters is None:
        data: dict[str, Any] = {}
    elif isinstance(filters, CallExportFilters):
        data = filters.model_dump()
    else:
        data = dict(filters)

    def _parse_date(value: str | None, *, end_of_day: bool = False) -> datetime | None:
        if not value or not str(value).strip():
            return None
        raw = str(value).strip()
        try:
            if len(raw) == 10:
                dt = datetime.fromisoformat(raw)
                if end_of_day:
                    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                return dt
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    return dict(
        status_filter=data.get("status_filter") or None,
        operator_match=data.get("operator_match") or None,
        operator_value=data.get("operator_value") or None,
        client_match=data.get("client_match") or None,
        client_value=data.get("client_value") or None,
        date_from=_parse_date(data.get("date_from")),
        date_to=_parse_date(data.get("date_to"), end_of_day=True),
        duration_op=data.get("duration_op") or None,
        duration_value=data.get("duration_value"),
        score_op=data.get("score_op") or None,
        score_value=data.get("score_value"),
        tag_id=data.get("tag_id"),
    )


def _row_from_call(call: Call, analysis: AnalysisResult | None, tag_names: list[str]) -> dict[str, Any]:
    ts = call.call_timestamp or call.created_at
    return {
        "id": call.id,
        "call_uuid": str(call.call_uuid),
        "operator_name": call.operator.full_name if call.operator else None,
        "direction": call.direction,
        "duration": call.duration,
        "client_number": call.client_number,
        "call_timestamp": ts.isoformat() if ts else None,
        "status": call.status,
        "total_score": analysis.total_score if analysis else None,
        "topic": analysis.topic if analysis else None,
        "summary": analysis.summary if analysis else None,
        "call_outcome": analysis.call_outcome if analysis else None,
        "tags": "; ".join(tag_names) if tag_names else "",
    }


def _analysis_map(rows: Iterable[tuple]) -> dict[int, AnalysisResult]:
    """Keep first (latest) analysis per call_id from ordered rows."""
    out: dict[int, AnalysisResult] = {}
    for call_id, ar in rows:
        if call_id not in out:
            out[call_id] = ar
    return out


async def fetch_export_rows_async(
    db: AsyncSession,
    *,
    ids: list[int] | None = None,
    filters: CallExportFilters | dict | None = None,
    limit: int = CALLS_EXPORT_MAX_ROWS,
) -> list[dict[str, Any]]:
    if ids:
        q = (
            select(Call)
            .where(Call.id.in_(ids))
            .options(
                selectinload(Call.operator),
                selectinload(Call.tags).selectinload(CallTag.tag),
            )
            .order_by(Call.id)
        )
        result = await db.execute(q)
        calls = list(result.scalars().unique().all())
        # Preserve request order when possible
        by_id = {c.id: c for c in calls}
        calls = [by_id[i] for i in ids if i in by_id]
    else:
        kw = parse_export_filters(filters)
        q = build_calls_list_query(**kw, sort_by="call_timestamp", sort_order="desc")
        q = q.options(
            selectinload(Call.operator),
            selectinload(Call.tags).selectinload(CallTag.tag),
        ).limit(limit)
        result = await db.execute(q)
        calls = list(result.scalars().unique().all())

    if not calls:
        return []

    call_ids = [c.id for c in calls]
    ar_result = await db.execute(
        select(AnalysisResult.call_id, AnalysisResult)
        .where(AnalysisResult.call_id.in_(call_ids))
        .order_by(AnalysisResult.call_id, AnalysisResult.created_at.desc())
    )
    analyses = _analysis_map(ar_result.all())

    rows: list[dict[str, Any]] = []
    for call in calls:
        tag_names = sorted({link.tag.name for link in call.tags if link.tag})
        rows.append(_row_from_call(call, analyses.get(call.id), tag_names))
    return rows


def fetch_export_rows_sync(
    db: Session,
    *,
    ids: list[int] | None = None,
    filters: CallExportFilters | dict | None = None,
    limit: int = CALLS_EXPORT_MAX_ROWS,
) -> list[dict[str, Any]]:
    if ids:
        q = (
            select(Call)
            .where(Call.id.in_(ids))
            .options(
                selectinload(Call.operator),
                selectinload(Call.tags).selectinload(CallTag.tag),
            )
            .order_by(Call.id)
        )
        calls = list(db.execute(q).scalars().unique().all())
        by_id = {c.id: c for c in calls}
        calls = [by_id[i] for i in ids if i in by_id]
    else:
        kw = parse_export_filters(filters)
        q = build_calls_list_query(**kw, sort_by="call_timestamp", sort_order="desc")
        q = q.options(
            selectinload(Call.operator),
            selectinload(Call.tags).selectinload(CallTag.tag),
        ).limit(limit)
        calls = list(db.execute(q).scalars().unique().all())

    if not calls:
        return []

    call_ids = [c.id for c in calls]
    ar_rows = db.execute(
        select(AnalysisResult.call_id, AnalysisResult)
        .where(AnalysisResult.call_id.in_(call_ids))
        .order_by(AnalysisResult.call_id, AnalysisResult.created_at.desc())
    ).all()
    analyses = _analysis_map(ar_rows)

    rows: list[dict[str, Any]] = []
    for call in calls:
        tag_names = sorted({link.tag.name for link in call.tags if link.tag})
        rows.append(_row_from_call(call, analyses.get(call.id), tag_names))
    return rows


async def count_export_rows_async(db: AsyncSession, filters: CallExportFilters | dict | None) -> int:
    kw = parse_export_filters(filters)
    return int(await db.scalar(build_calls_count_query(**kw)) or 0)


def count_export_rows_sync(db: Session, filters: CallExportFilters | dict | None) -> int:
    kw = parse_export_filters(filters)
    return int(db.scalar(build_calls_count_query(**kw)) or 0)


def export_calls_to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def export_calls_json_bytes(rows: list[dict[str, Any]]) -> bytes:
    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "count": len(rows),
        "calls": rows,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def encode_export_file(rows: list[dict[str, Any]], fmt: str) -> tuple[bytes, str, str]:
    """Return (content, media_type, filename)."""
    if fmt == "csv":
        content = ("\ufeff" + export_calls_to_csv(rows)).encode("utf-8")
        return content, "text/csv; charset=utf-8", calls_export_filename(ext="csv")
    content = export_calls_json_bytes(rows)
    return content, "application/json; charset=utf-8", calls_export_filename(ext="json")
