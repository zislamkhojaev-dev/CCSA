import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from celery import Task
from sqlalchemy import select

from app.models import Call, Operator, SyncRun
from app.services.storage import storage_service
from app.services.webitel import WebitelClient
from worker.celery_app import celery_app
from worker.db import get_sync_session
from worker.schedule_utils import cron_matches_now, is_within_sync_window, parse_sync_days
from worker.settings_sync import get_setting_sync
from worker.tasks.pipeline import transcribe_call

logger = logging.getLogger(__name__)


class WebitelTask(Task):
    autoretry_for = (Exception,)
    retry_backoff = True
    max_retries = 3


def _parse_item(item: dict) -> tuple[str, str | None, dict]:
    call_uuid = str(item.get("id") or item.get("uuid") or uuid.uuid4())
    files = item.get("files") or []
    file_id = str(files[0].get("id") or files[0].get("file_id") or "") if files else None
    return call_uuid, file_id, item


def _resolve_operator(db, webitel_agent_id: str, operator_name: str, cache: dict[str, int]) -> int:
    if webitel_agent_id and webitel_agent_id in cache:
        return cache[webitel_agent_id]
    operator = None
    if webitel_agent_id:
        operator = db.execute(
            select(Operator).where(Operator.webitel_id == webitel_agent_id)
        ).scalar_one_or_none()
    if not operator:
        operator = Operator(webitel_id=webitel_agent_id or None, full_name=operator_name, is_active=True)
        db.add(operator)
        db.flush()
    if webitel_agent_id:
        cache[webitel_agent_id] = operator.id
    return operator.id


def _import_one_call(client: WebitelClient, item: dict, operator_cache: dict[str, int]) -> str:
    call_uuid_str, file_id, raw = _parse_item(item)
    try:
        call_uuid = uuid.UUID(call_uuid_str)
    except ValueError:
        call_uuid = uuid.uuid4()

    with get_sync_session() as db:
        if db.execute(select(Call.id).where(Call.call_uuid == call_uuid)).scalar_one_or_none():
            return "skipped"

        webitel_agent_id = str(raw.get("agent_id") or raw.get("user_id") or "")
        operator_name = raw.get("agent_name") or raw.get("user_name") or "Unknown"
        operator_id = _resolve_operator(db, webitel_agent_id, operator_name, operator_cache)

        ts = raw.get("created_at") or raw.get("timestamp")
        call_ts = datetime.utcnow()
        if isinstance(ts, (int, float)):
            call_ts = datetime.utcfromtimestamp(ts / 1000 if ts > 1e12 else ts)

        call = Call(
            call_uuid=call_uuid,
            operator_id=operator_id,
            direction=raw.get("direction"),
            duration=raw.get("duration") or raw.get("bill_sec"),
            client_number=str(raw.get("destination") or raw.get("from") or raw.get("caller") or ""),
            call_timestamp=call_ts,
            status="downloading",
            source="webitel",
        )
        db.add(call)
        db.flush()
        call_id = call.id

    if not file_id:
        with get_sync_session() as db:
            call = db.get(Call, call_id)
            if call:
                call.status = "error"
                call.error_message = "No recording file"
        return "error"

    try:
        audio = asyncio.run(client.download_recording(file_id))
        key = storage_service.upload_bytes(audio, "calls", f"{call_uuid}.wav")
    except Exception as e:
        with get_sync_session() as db:
            call = db.get(Call, call_id)
            if call:
                call.status = "error"
                call.error_message = f"Download failed: {e}"
        return "error"

    with get_sync_session() as db:
        call = db.get(Call, call_id)
        if not call:
            return "error"
        call.audio_path = key
        call.status = "pending"
        call.error_message = None
    transcribe_call.delay(call_id)
    return "imported"


@celery_app.task(name="worker.tasks.webitel.sync_webitel_calls", base=WebitelTask, bind=True)
def sync_webitel_calls(self) -> None:
    with get_sync_session() as db:
        days = parse_sync_days(get_setting_sync(db, "webitel_sync_days", "[0,1,2,3,4]"))
        cron = get_setting_sync(db, "webitel_sync_cron", "*/30 * * * *")
        if not cron_matches_now(cron):
            return
        if not is_within_sync_window(
            active_days=days,
            time_from=get_setting_sync(db, "webitel_sync_time_from", "09:00"),
            time_to=get_setting_sync(db, "webitel_sync_time_to", "18:00"),
        ):
            logger.info("Webitel sync skipped: outside configured window")
            return

        run = SyncRun(source="webitel_api", status="running")
        db.add(run)
        db.flush()
        run_id = run.id

        api_url = get_setting_sync(db, "webitel_api_url")
        token = get_setting_sync(db, "webitel_access_token")
        if not api_url:
            run.status = "skipped"
            run.finished_at = datetime.utcnow()
            run.stats_json = {"reason": "webitel not configured"}
            return

        client = WebitelClient(api_url, token)
        fetch_error: Exception | None = None
        items: list = []
        try:
            items = asyncio.run(
                client.fetch_call_history(
                    created_from=datetime.utcnow() - timedelta(hours=24),
                    created_to=datetime.utcnow(),
                )
            )
        except Exception as e:
            run.status = "error"
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()
            logger.exception("Webitel sync failed")
            fetch_error = e

    if fetch_error:
        raise fetch_error

    imported = skipped = errors = 0
    operator_cache: dict[str, int] = {}
    for item in items:
        try:
            result = _import_one_call(client, item, operator_cache)
            if result == "skipped":
                skipped += 1
            elif result == "imported":
                imported += 1
            else:
                errors += 1
        except Exception:
            errors += 1
            logger.exception("Webitel import failed for item")

    with get_sync_session() as db:
        run = db.get(SyncRun, run_id)
        if run:
            run.status = "completed"
            run.finished_at = datetime.utcnow()
            run.stats_json = {
                "imported": imported,
                "skipped": skipped,
                "errors": errors,
                "total_items": len(items),
            }


@celery_app.task(name="worker.tasks.webitel.sync_operators_from_webitel", base=WebitelTask)
def sync_operators_from_webitel() -> dict:
    from app.services.operator_sync import extract_operators, operator_lookback_start

    with get_sync_session() as db:
        api_url = get_setting_sync(db, "webitel_api_url")
        token = get_setting_sync(db, "webitel_access_token")
        if not api_url:
            logger.info("Operator sync skipped: Webitel API URL is not configured")
            return {"created": 0, "found": 0}
        client = WebitelClient(api_url, token)
        try:
            items = asyncio.run(client.fetch_call_history(created_from=operator_lookback_start()))
        except Exception as e:
            logger.warning("Operator sync failed: %s", e)
            return {"created": 0, "found": 0}

        pairs = extract_operators(items)
        created = 0
        for webitel_id, full_name in pairs:
            exists = db.execute(
                select(Operator.id).where(Operator.webitel_id == webitel_id)
            ).scalar_one_or_none()
            if exists:
                continue
            db.add(Operator(webitel_id=webitel_id, full_name=full_name, is_active=True))
            created += 1

    logger.info("Operator sync done: created=%s found=%s", created, len(pairs))
    return {"created": created, "found": len(pairs)}
