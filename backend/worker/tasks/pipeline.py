import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from celery import Task

from app.models import AnalysisResult, Call, CallStatus, Transcription
from worker.celery_app import celery_app
from worker.db import get_sync_session
from worker.llm_context import run_llm_analysis
from worker.task_lock import call_task_lock, is_locked
from app.services.call_utils import duration_seconds_from_transcription

logger = logging.getLogger(__name__)
STT_URL = os.getenv("STT_SERVICE_URL", "http://stt-service:8001")

ANALYSIS_LOCK_TTL = 1800
TRANSCRIBE_LOCK_TTL = 3600
# A call left in a processing state longer than this, with no worker holding its
# lock, is treated as abandoned and re-queued.
STALE_PROCESSING_MINUTES = 30
PROCESSING_STATUSES = (
    CallStatus.downloading.value,
    CallStatus.transcribing.value,
    CallStatus.analyzing.value,
)


def _mark_call(call_id: int, status: str, *, error_message: str | None = None) -> None:
    """Persist a status change in its own transaction so it survives task failure."""
    with get_sync_session() as db:
        call = db.get(Call, call_id)
        if call:
            call.status = status
            call.error_message = error_message


class PipelineTask(Task):
    # Do not retry business-logic failures (missing transcript, bad data).
    autoretry_for = (httpx.HTTPError, httpx.TimeoutException, ConnectionError)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 3


def _transcribe_audio(
    storage_key: str,
    asr_model: str | None = None,
    diarization_method: str | None = None,
) -> dict:
    from worker.asr_limit import asr_concurrency_slot
    from worker.asr_settings import asr_http_timeout_sec, asr_max_parallel

    payload: dict = {"storage_key": storage_key}
    if asr_model:
        payload["model"] = asr_model
    if diarization_method:
        payload["diarization_method"] = diarization_method

    with get_sync_session() as db:
        max_parallel = asr_max_parallel(db)
        timeout_sec = asr_http_timeout_sec(db)

    with asr_concurrency_slot(
        max_parallel,
        acquire_timeout=min(timeout_sec + 120.0, 900.0),
        slot_ttl=timeout_sec + 180.0,
    ):
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(f"{STT_URL}/transcribe", json=payload)
            r.raise_for_status()
            return r.json()


@celery_app.task(name="worker.tasks.pipeline.transcribe_call", base=PipelineTask, bind=True)
def transcribe_call(self, call_id: int) -> None:
    from worker.settings_sync import get_setting_sync

    with call_task_lock("transcribe", call_id, ttl=TRANSCRIBE_LOCK_TTL) as acquired:
        if not acquired:
            logger.info("Skip transcribe_call %s — another worker is running it", call_id)
            return

        with get_sync_session() as db:
            call = db.get(Call, call_id)
            if not call or not call.audio_path:
                return
            call.status = CallStatus.transcribing.value
            call.error_message = None
            audio_path = call.audio_path

        try:
            with get_sync_session() as db:
                asr_model = get_setting_sync(db, "asr_model", "")
                diarization_method = get_setting_sync(db, "asr_diarization_method", "")
            result = _transcribe_audio(
                audio_path,
                asr_model or None,
                diarization_method or None,
            )
            with get_sync_session() as db:
                call = db.get(Call, call_id)
                if not call:
                    return
                db.add(
                    Transcription(
                        call_id=call.id,
                        full_text=result.get("full_text"),
                        utterances=result.get("utterances"),
                        model_name=result.get("model_name"),
                    )
                )
                call.duration = duration_seconds_from_transcription(result)
                call.status = CallStatus.transcribed.value
                call.error_message = None
        except Exception as e:
            _mark_call(call_id, CallStatus.error.value, error_message=str(e)[:1000])
            logger.exception("Transcribe failed for call %s", call_id)
            raise

    analyze_call.delay(call_id)


@celery_app.task(name="worker.tasks.pipeline.analyze_call", base=PipelineTask, bind=True)
def analyze_call(self, call_id: int, scenario_id: int | None = None) -> None:
    from sqlalchemy import delete

    from worker.llm_context import resolve_scenario
    from worker.settings_sync import get_setting_sync

    with call_task_lock("analyze", call_id, ttl=ANALYSIS_LOCK_TTL) as acquired:
        if not acquired:
            logger.info("Skip analyze_call %s — another worker is running it", call_id)
            return

        with get_sync_session() as db:
            call = db.get(Call, call_id)
            if not call:
                return
            call.status = CallStatus.analyzing.value
            call.error_message = None

        try:
            # The LLM call can take minutes: keep it out of the transaction that
            # writes the result, so no row lock is held while waiting.
            with get_sync_session() as db:
                call = db.get(Call, call_id)
                if not call:
                    return
                output = run_llm_analysis(db, call, scenario_id, strict=True)
                scenario = resolve_scenario(db, call, scenario_id)
                resolved_scenario_id = scenario.id if scenario else None
                llm_model = get_setting_sync(db, "llm_model", "gpt-4o-mini")
                criteria_json = {k: v.model_dump() for k, v in output.criteria_results.items()}

            with get_sync_session() as db:
                call = db.get(Call, call_id)
                if not call:
                    return
                # Re-analysis replaces the previous verdict instead of stacking rows,
                # otherwise dashboard aggregates count the same call twice.
                db.execute(delete(AnalysisResult).where(AnalysisResult.call_id == call_id))
                db.add(
                    AnalysisResult(
                        call_id=call.id,
                        llm_model=llm_model,
                        total_score=output.total_score,
                        is_violation=output.is_violation,
                        summary=output.summary,
                        client_pains=output.client_pains,
                        call_outcome=output.call_outcome,
                        topic=output.topic,
                        criteria_results=criteria_json,
                    )
                )
                if resolved_scenario_id:
                    call.scenario_id = resolved_scenario_id
                call.status = CallStatus.analyzed.value
                call.error_message = None
        except Exception as e:
            _mark_call(call_id, CallStatus.error.value, error_message=str(e)[:1000])
            logger.exception("Analysis failed for call %s", call_id)
            raise


@celery_app.task(name="worker.tasks.pipeline.reanalyze_call", base=PipelineTask)
def reanalyze_call(call_id: int, scenario_id: int | None = None) -> None:
    analyze_call(call_id, scenario_id)


@celery_app.task(name="worker.tasks.pipeline.retranscribe_call", base=PipelineTask)
def retranscribe_call(call_id: int) -> None:
    """Re-run ASR then LLM (deletes previous transcription rows)."""
    from sqlalchemy import delete

    if is_locked("transcribe", call_id):
        logger.info("Skip retranscribe_call %s — transcription already running", call_id)
        return

    with get_sync_session() as db:
        call = db.get(Call, call_id)
        if not call or not call.audio_path:
            return
        db.execute(delete(Transcription).where(Transcription.call_id == call_id))
        db.execute(delete(AnalysisResult).where(AnalysisResult.call_id == call_id))
        call.status = CallStatus.transcribing.value
        call.error_message = None
    transcribe_call.delay(call_id)


@celery_app.task(name="worker.tasks.pipeline.backfill_topics", base=PipelineTask)
def backfill_topics(limit: int = 200) -> dict:
    """Classify topic for analyzed calls that have no topic yet (post-migration backfill)."""
    import asyncio
    import json

    from sqlalchemy import or_, select

    from app.models import Transcription
    from app.services.llm import classify_topic
    from app.services.quality_settings import DEFAULT_TAXONOMY, parse_topics, UNCLASSIFIED_TOPIC
    from worker.llm_context import get_llm_kwargs
    from worker.settings_sync import get_setting_sync

    processed = 0
    skipped = 0
    errors = 0

    with get_sync_session() as db:
        kwargs = get_llm_kwargs(db)
        llm_model = get_setting_sync(db, "llm_model", "gpt-4o-mini")
        topics = parse_topics(
            get_setting_sync(db, "call_topics", json.dumps(DEFAULT_TAXONOMY, ensure_ascii=False))
        )
        result_ids = list(
            db.execute(
                select(AnalysisResult.id)
                .where(
                    or_(
                        AnalysisResult.topic.is_(None),
                        AnalysisResult.topic == UNCLASSIFIED_TOPIC,
                    )
                )
                .order_by(AnalysisResult.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

    for result_id in result_ids:
        try:
            with get_sync_session() as db:
                res = db.get(AnalysisResult, result_id)
                if not res or (res.topic is not None and res.topic != UNCLASSIFIED_TOPIC):
                    continue
                trans = db.execute(
                    select(Transcription)
                    .where(Transcription.call_id == res.call_id)
                    .order_by(Transcription.created_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if not trans or not trans.full_text:
                    skipped += 1
                    continue
                topic = asyncio.run(
                    classify_topic(trans.full_text, topics, model=llm_model, **kwargs)
                )
                res.topic = topic or UNCLASSIFIED_TOPIC
                processed += 1
        except Exception:
            errors += 1
            logger.exception("backfill_topics failed for analysis_result %s", result_id)

    logger.info(
        "backfill_topics done: processed=%s skipped=%s errors=%s",
        processed,
        skipped,
        errors,
    )
    return {"processed": processed, "skipped": skipped, "errors": errors}


@celery_app.task(name="worker.tasks.pipeline.recover_stuck_calls", base=PipelineTask)
def recover_stuck_calls(stale_minutes: int | None = None) -> dict:
    """Re-queue calls abandoned in a processing state by a crashed/restarted worker.

    A call qualifies only when no worker holds its Redis lock, so runs in progress
    are never interrupted.
    """
    from sqlalchemy import func, or_, select

    minutes = STALE_PROCESSING_MINUTES if stale_minutes is None else max(0, int(stale_minutes))
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    requeued = 0
    failed = 0
    running = 0

    with get_sync_session() as db:
        stuck = db.execute(
            select(Call.id, Call.status).where(
                Call.status.in_(PROCESSING_STATUSES),
                or_(Call.updated_at.is_(None), Call.updated_at <= cutoff),
            )
        ).all()

        for call_id, status in stuck:
            kind = "analyze" if status == CallStatus.analyzing.value else "transcribe"
            if is_locked(kind, call_id):
                running += 1
                continue

            call = db.get(Call, call_id)
            if not call:
                continue

            has_transcript = bool(
                db.scalar(
                    select(func.count())
                    .select_from(Transcription)
                    .where(Transcription.call_id == call_id)
                )
            )
            if status == CallStatus.analyzing.value and has_transcript:
                call.status = CallStatus.transcribed.value
                call.error_message = None
                requeued += 1
            elif call.audio_path:
                call.status = CallStatus.pending.value
                call.error_message = None
                requeued += 1
            else:
                call.status = CallStatus.error.value
                call.error_message = "Обработка прервана, а исходный файл недоступен"
                failed += 1

    logger.info(
        "recover_stuck_calls done: requeued=%s failed=%s still_running=%s (stale>%sm)",
        requeued,
        failed,
        running,
        minutes,
    )
    return {"requeued": requeued, "failed": failed, "running": running}


@celery_app.task(name="worker.tasks.pipeline.process_pending_batch", base=PipelineTask)
def process_pending_batch() -> None:
    from sqlalchemy import select

    from app.models import AutomationRule
    from worker.schedule_utils import is_within_sync_window
    from worker.settings_sync import get_setting_sync

    with get_sync_session() as db:
        rule = db.execute(select(AutomationRule).where(AutomationRule.is_enabled.is_(True)).limit(1)).scalar_one_or_none()
        if rule and not is_within_sync_window(
            active_days=rule.active_days,
            time_from=rule.time_from,
            time_to=rule.time_to,
        ):
            logger.info(
                "Pending batch skipped: outside automation window (%s–%s, days=%s)",
                rule.time_from,
                rule.time_to,
                rule.active_days,
            )
            return

        batch_size = rule.batch_size if rule else int(get_setting_sync(db, "automation_batch_size", "10"))

        pending = (
            db.execute(
                select(Call)
                .where(Call.status.in_(["pending", "transcribed"]))
                .order_by(Call.created_at)
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        for call in pending:
            if call.status == "pending" and call.audio_path:
                transcribe_call.delay(call.id)
            elif call.status == "transcribed":
                analyze_call.delay(call.id)
