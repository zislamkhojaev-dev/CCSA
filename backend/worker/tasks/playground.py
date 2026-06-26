import logging
import uuid

import httpx
from celery import Task
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import AnalysisResult, Call, Criterion, PlaygroundFile, PlaygroundJob, PlaygroundResult, Scenario, Transcription
from app.services.call_utils import duration_seconds_from_transcription
from app.services.redis_events import publish_playground_event
from worker.celery_app import celery_app
from worker.db import get_sync_session
from worker.llm_context import get_llm_kwargs
from worker.tasks.pipeline import _transcribe_audio

logger = logging.getLogger(__name__)


class PlaygroundTask(Task):
    autoretry_for = (httpx.HTTPError, httpx.TimeoutException, ConnectionError)
    retry_backoff = True
    max_retries = 2


def _emit(job_id: int, file_id: int, status: str, done: bool = False, error: str | None = None):
    publish_playground_event(
        job_id,
        {"file_id": file_id, "status": status, "done": done, "error": error},
    )


def _update_playground_job_status(job_id: int) -> None:
    with get_sync_session() as db:
        job = db.execute(
            select(PlaygroundJob).where(PlaygroundJob.id == job_id).options(selectinload(PlaygroundJob.files))
        ).scalar_one_or_none()
        if not job:
            return
        if any(f.status in ("transcribing", "analyzing", "queued") for f in job.files):
            job.status = "processing"
            return
        if all(f.status in ("ready", "error") for f in job.files):
            job.status = "completed" if any(f.status == "ready" for f in job.files) else "error"


def _schedule_playground_queue(job_id: int) -> None:
    """When sequential mode is on, start the next queued file after the current one finishes."""
    from worker.asr_settings import playground_sequential

    with get_sync_session() as db:
        if not playground_sequential(db):
            return
        job = db.execute(
            select(PlaygroundJob).where(PlaygroundJob.id == job_id).options(selectinload(PlaygroundJob.files))
        ).scalar_one_or_none()
        if not job:
            return
        if any(f.status in ("transcribing", "analyzing") for f in job.files):
            return
        pending = sorted((f for f in job.files if f.status == "queued"), key=lambda f: f.id)
        if pending:
            process_playground_file.delay(pending[0].id)


def _load_playground_file(db, file_id: int) -> tuple[PlaygroundFile, PlaygroundJob] | tuple[None, None]:
    pf = db.execute(
        select(PlaygroundFile)
        .where(PlaygroundFile.id == file_id)
        .options(selectinload(PlaygroundFile.job))
    ).scalar_one_or_none()
    if not pf:
        return None, None
    return pf, pf.job


@celery_app.task(name="worker.tasks.playground.process_playground_file", base=PlaygroundTask, bind=True)
def process_playground_file(self, file_id: int) -> None:
    import asyncio

    from app.services.llm import analyze_transcript
    from worker.settings_sync import get_setting_sync as gss

    job_id: int | None = None
    storage_key: str | None = None

    with get_sync_session() as db:
        pf, job = _load_playground_file(db, file_id)
        if not pf or not job:
            return
        if pf.status not in ("queued", "error", "transcribing"):
            logger.info("Skip playground file %s — status %s", file_id, pf.status)
            return
        job_id = job.id
        storage_key = pf.storage_key
        pf.status = "transcribing"
        pf.error_message = None
        job.status = "processing"

    _emit(job_id, file_id, "transcribing")

    try:
        with get_sync_session() as db:
            asr_model = gss(db, "asr_model", "")
            diarization_method = gss(db, "asr_diarization_method", "")
        result = _transcribe_audio(
            storage_key,
            asr_model or None,
            diarization_method or None,
        )

        with get_sync_session() as db:
            pf, job = _load_playground_file(db, file_id)
            if not pf or not job:
                return
            pf.status = "analyzing"
        _emit(job_id, file_id, "analyzing")

        analysis_data = None
        with get_sync_session() as db:
            pf, job = _load_playground_file(db, file_id)
            if not pf or not job:
                return
            scenario = db.get(Scenario, job.scenario_id) if job.scenario_id else None
            if not scenario:
                scenario = db.execute(
                    select(Scenario).where(Scenario.is_active.is_(True)).limit(1)
                ).scalar_one_or_none()

            if scenario and result.get("full_text"):
                criteria = list(
                    db.execute(
                        select(Criterion).where(Criterion.scenario_id == scenario.id).order_by(Criterion.sort_order)
                    ).scalars()
                )
                kwargs = get_llm_kwargs(db)
                custom = job.custom_prompt if not job.use_scenario_prompt else None
                output = asyncio.run(
                    analyze_transcript(
                        scenario,
                        criteria,
                        result["full_text"],
                        custom_system_prompt=custom,
                        model=gss(db, "llm_model", scenario.llm_model),
                        **kwargs,
                    )
                )
                analysis_data = output.model_dump(mode="json")

            existing = db.execute(
                select(PlaygroundResult).where(PlaygroundResult.file_id == pf.id)
            ).scalar_one_or_none()
            if existing:
                existing.transcription = result
                existing.analysis = analysis_data
            else:
                db.add(PlaygroundResult(file_id=pf.id, transcription=result, analysis=analysis_data))
            pf.status = "ready"
        _emit(job_id, file_id, "ready", done=True)
        if job_id is not None:
            _schedule_playground_queue(job_id)
            _update_playground_job_status(job_id)
    except Exception as e:
        logger.exception("Playground file %s failed", file_id)
        if job_id is not None:
            with get_sync_session() as db:
                pf, job = _load_playground_file(db, file_id)
                if pf and job:
                    pf.status = "error"
                    pf.error_message = str(e)[:500]
            _emit(job_id, file_id, "error", done=True, error=str(e))
            _schedule_playground_queue(job_id)
            _update_playground_job_status(job_id)
        raise


def promote_playground_file(file_id: int) -> int:
    with get_sync_session() as db:
        pf = db.execute(
            select(PlaygroundFile)
            .where(PlaygroundFile.id == file_id)
            .options(selectinload(PlaygroundFile.job), selectinload(PlaygroundFile.result))
        ).scalar_one_or_none()
        if not pf or not pf.result:
            raise ValueError("File not ready")

        trans = pf.result.transcription or {}
        call = Call(
            call_uuid=uuid.uuid4(),
            scenario_id=pf.job.scenario_id,
            audio_path=pf.storage_key,
            call_timestamp=pf.created_at,
            duration=duration_seconds_from_transcription(trans),
            status="analyzed",
            source="playground",
        )
        db.add(call)
        db.flush()
        db.add(
            Transcription(
                call_id=call.id,
                full_text=trans.get("full_text"),
                utterances=trans.get("utterances"),
                model_name=trans.get("model_name"),
            )
        )
        if pf.result.analysis:
            a = pf.result.analysis
            db.add(
                AnalysisResult(
                    call_id=call.id,
                    llm_model=a.get("llm_model"),
                    total_score=a.get("total_score"),
                    is_violation=a.get("is_violation", False),
                    summary=a.get("summary"),
                    client_pains=a.get("client_pains"),
                    call_outcome=a.get("call_outcome"),
                    criteria_results=a.get("criteria_results"),
                )
            )
        return call.id


def promote_playground_job(job_id: int) -> list[int]:
    with get_sync_session() as db:
        job = db.execute(
            select(PlaygroundJob)
            .where(PlaygroundJob.id == job_id)
            .options(selectinload(PlaygroundJob.files).selectinload(PlaygroundFile.result))
        ).scalar_one_or_none()
        if not job:
            raise ValueError("Job not found")
        ready_ids = [f.id for f in job.files if f.status == "ready" and f.result]
    if not ready_ids:
        raise ValueError("No ready files")
    call_ids: list[int] = []
    for file_id in ready_ids:
        call_ids.append(promote_playground_file(file_id))
    return call_ids
