import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx
from celery import Task

from app.models import ResearchStudy
from app.schemas.research import ResearchFilters
from app.services.llm import CohortCall, run_cohort_analysis
from app.services.redis_events import publish_research_event
from app.services.research_query import build_research_calls_by_ids_query, build_research_calls_query
from app.services.research_utils import filters_to_query_kwargs, research_max_calls
from worker.celery_app import celery_app
from worker.db import get_sync_session
from worker.llm_context import get_llm_kwargs
from worker.settings_sync import get_setting_sync

logger = logging.getLogger(__name__)


class ResearchTask(Task):
    autoretry_for = (httpx.HTTPError, httpx.TimeoutException, ConnectionError)
    retry_backoff = True
    max_retries = 2


def _emit(study_id: int, *, done: bool = False, error: str | None = None, **extra: Any) -> None:
    payload: dict[str, Any] = {"study_id": study_id, **extra}
    if done:
        payload["done"] = True
    if error:
        payload["error"] = error
    publish_research_event(study_id, payload)


@celery_app.task(name="worker.tasks.research.run_research_study", base=ResearchTask, bind=True)
def run_research_study(self, study_id: int) -> None:
    with get_sync_session() as db:
        study = db.get(ResearchStudy, study_id)
        if not study:
            return
        if study.status not in ("pending", "running"):
            return
        study.status = "running"
        study.error_message = None
        user_prompt = study.prompt
        filters = ResearchFilters.model_validate(study.filters_json or {})
        kw = filters_to_query_kwargs(filters)
        call_ids_snapshot = study.call_ids if isinstance(study.call_ids, list) else None

    _emit(study_id, status="running", phase="starting")

    try:
        with get_sync_session() as db:
            max_calls = research_max_calls()
            if call_ids_snapshot:
                rows = db.execute(build_research_calls_by_ids_query(call_ids_snapshot)).all()
            else:
                rows = db.execute(build_research_calls_query(**kw).limit(max_calls)).all()
            cohort = [
                CohortCall(
                    call_id=row[0],
                    call_timestamp=row[1],
                    direction=row[2],
                    duration=row[3],
                    operator_name=row[4],
                    full_text=row[5] or "",
                )
                for row in rows
            ]
            if not cohort:
                study = db.get(ResearchStudy, study_id)
                if study:
                    msg = (
                        "Не удалось загрузить звонки исследования: транскрипты отсутствуют "
                        "или звонки были удалены"
                    )
                    study.status = "error"
                    study.error_message = msg
                    study.finished_at = datetime.utcnow()
                    _emit(study_id, status="error", done=True, error=msg)
                return

            llm_kwargs = get_llm_kwargs(db)
            model_name = get_setting_sync(db, "llm_model", "gpt-4o-mini")

        _emit(study_id, status="running", phase="loaded", call_count=len(cohort))

        def on_progress(data: dict[str, Any]) -> None:
            _emit(study_id, status="running", **data)

        report = asyncio.run(
            run_cohort_analysis(
                user_prompt,
                cohort,
                model=model_name,
                on_progress=on_progress,
                **llm_kwargs,
            )
        )

        with get_sync_session() as db:
            study = db.get(ResearchStudy, study_id)
            if not study:
                return
            study.status = "completed"
            study.call_count = len(cohort)
            study.call_ids = [c.call_id for c in cohort]
            study.llm_model = model_name
            study.report_markdown = report
            study.finished_at = datetime.utcnow()

        _emit(study_id, status="completed", done=True, call_count=len(cohort))

    except Exception as e:
        logger.exception("Research study %s failed", study_id)
        err = str(e)[:2000]
        with get_sync_session() as db:
            study = db.get(ResearchStudy, study_id)
            if study:
                study.status = "error"
                study.error_message = err
                study.finished_at = datetime.utcnow()
        _emit(study_id, status="error", done=True, error=err)
        raise
