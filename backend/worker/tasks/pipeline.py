import logging
import os

import httpx
from celery import Task

from app.models import AnalysisResult, Call, Transcription
from worker.celery_app import celery_app
from worker.db import get_sync_session
from worker.llm_context import run_llm_analysis
from app.services.call_utils import duration_seconds_from_transcription

logger = logging.getLogger(__name__)
STT_URL = os.getenv("STT_SERVICE_URL", "http://stt-service:8001")


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

    with get_sync_session() as db:
        call = db.get(Call, call_id)
        if not call or not call.audio_path:
            return
        if call.status in ("transcribing", "analyzing"):
            logger.info("Skip transcribe_call %s — already %s", call_id, call.status)
            return
        call.status = "transcribing"
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
            call.status = "transcribed"
    except Exception as e:
        with get_sync_session() as db:
            call = db.get(Call, call_id)
            if call:
                call.status = "error"
                call.error_message = str(e)
        logger.exception("Transcribe failed for call %s", call_id)
        raise
    analyze_call.delay(call_id)


@celery_app.task(name="worker.tasks.pipeline.analyze_call", base=PipelineTask, bind=True)
def analyze_call(self, call_id: int, scenario_id: int | None = None) -> None:
    with get_sync_session() as db:
        call = db.get(Call, call_id)
        if not call:
            return
        if call.status == "analyzing":
            logger.info("Skip analyze_call %s — already analyzing", call_id)
            return
        call.status = "analyzing"
        db.flush()
        try:
            from worker.llm_context import resolve_scenario
            from worker.settings_sync import get_setting_sync

            output = run_llm_analysis(db, call, scenario_id)
            scenario = resolve_scenario(db, call, scenario_id)
            if scenario:
                call.scenario_id = scenario.id
            criteria_json = {k: v.model_dump() for k, v in output.criteria_results.items()}
            db.add(
                AnalysisResult(
                    call_id=call.id,
                    llm_model=get_setting_sync(db, "llm_model", "gpt-4o-mini"),
                    total_score=output.total_score,
                    is_violation=output.is_violation,
                    summary=output.summary,
                    client_pains=output.client_pains,
                    call_outcome=output.call_outcome,
                    criteria_results=criteria_json,
                )
            )
            call.status = "analyzed"
            call.error_message = None
        except Exception as e:
            call.status = "error"
            call.error_message = str(e)
            logger.exception("Analysis failed for call %s", call_id)
            raise


@celery_app.task(name="worker.tasks.pipeline.reanalyze_call", base=PipelineTask)
def reanalyze_call(call_id: int, scenario_id: int | None = None) -> None:
    analyze_call(call_id, scenario_id)


@celery_app.task(name="worker.tasks.pipeline.retranscribe_call", base=PipelineTask)
def retranscribe_call(call_id: int) -> None:
    """Re-run ASR then LLM (deletes previous transcription rows)."""
    from sqlalchemy import delete

    with get_sync_session() as db:
        call = db.get(Call, call_id)
        if not call or not call.audio_path:
            return
        if call.status in ("transcribing", "analyzing"):
            logger.info("Skip retranscribe_call %s — already %s", call_id, call.status)
            return
        db.execute(delete(Transcription).where(Transcription.call_id == call_id))
        db.execute(delete(AnalysisResult).where(AnalysisResult.call_id == call_id))
        if call.status != "transcribing":
            call.status = "transcribing"
        call.error_message = None
        db.flush()
    transcribe_call.delay(call_id)


@celery_app.task(name="worker.tasks.pipeline.process_pending_batch", base=PipelineTask)
def process_pending_batch() -> None:
    from sqlalchemy import select

    from app.models import AutomationRule
    from worker.schedule_utils import is_within_sync_window, parse_sync_days
    from worker.settings_sync import get_setting_sync

    with get_sync_session() as db:
        rule = db.execute(select(AutomationRule).where(AutomationRule.is_enabled.is_(True)).limit(1)).scalar_one_or_none()
        if rule and not is_within_sync_window(
            active_days=rule.active_days,
            time_from=rule.time_from,
            time_to=rule.time_to,
        ):
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
