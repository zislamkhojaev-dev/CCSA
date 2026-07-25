"""Celery task: build call export file and store in MinIO."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.models import CallExportJob
from app.services.calls_export import (
    CALLS_EXPORT_MAX_ROWS,
    encode_export_file,
    fetch_export_rows_sync,
)
from app.services.redis_events import publish_call_export_event
from app.services.storage import storage_service
from worker.celery_app import celery_app
from worker.db import get_sync_session

logger = logging.getLogger(__name__)


def _emit(job_id: int, *, done: bool = False, error: str | None = None, **extra: Any) -> None:
    payload: dict[str, Any] = {"job_id": job_id, **extra}
    if done:
        payload["done"] = True
    if error:
        payload["error"] = error
    publish_call_export_event(job_id, payload)


@celery_app.task(name="worker.tasks.calls_export.run_calls_export")
def run_calls_export(job_id: int) -> dict:
    with get_sync_session() as db:
        job = db.get(CallExportJob, job_id)
        if not job:
            return {"ok": False, "error": "not_found"}
        if job.status not in ("pending", "running"):
            return {"ok": False, "status": job.status}
        job.status = "running"
        job.error_message = None
        fmt = job.format
        filters = job.filters_json or {}

    _emit(job_id, status="running")

    try:
        with get_sync_session() as db:
            rows = fetch_export_rows_sync(db, filters=filters, limit=CALLS_EXPORT_MAX_ROWS)
            content, media_type, _filename = encode_export_file(rows, fmt)
            key = f"exports/calls/{job_id}.{fmt}"
            storage_service.put_bytes(key, content, content_type=media_type.split(";")[0].strip())

            job = db.get(CallExportJob, job_id)
            if not job:
                return {"ok": False, "error": "not_found"}
            job.status = "completed"
            job.row_count = len(rows)
            job.storage_path = key
            job.finished_at = datetime.now(UTC)
            job.error_message = None

        _emit(job_id, status="completed", row_count=len(rows), done=True)
        logger.info("Call export job %s completed: %s rows", job_id, len(rows))
        return {"ok": True, "row_count": len(rows)}
    except Exception as e:
        logger.exception("Call export job %s failed", job_id)
        with get_sync_session() as db:
            job = db.get(CallExportJob, job_id)
            if job:
                job.status = "error"
                job.error_message = str(e)[:500]
                job.finished_at = datetime.now(UTC)
        _emit(job_id, status="error", error=str(e)[:500], done=True)
        return {"ok": False, "error": str(e)}
