import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_prerun, worker_process_init

broker = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery_app = Celery("ccsa", broker=broker, backend=backend)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Tashkent",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_default_queue="io",
    task_routes={
        "worker.tasks.pipeline.transcribe_call": {"queue": "stt"},
        "worker.tasks.pipeline.retranscribe_call": {"queue": "stt"},
        "worker.tasks.playground.process_playground_file": {"queue": "stt"},
        "worker.tasks.pipeline.analyze_call": {"queue": "llm"},
        "worker.tasks.pipeline.reanalyze_call": {"queue": "llm"},
        "worker.tasks.pipeline.backfill_topics": {"queue": "llm"},
        "worker.tasks.research.run_research_study": {"queue": "llm"},
        "worker.tasks.pipeline.process_pending_batch": {"queue": "io"},
        "worker.tasks.pipeline.recover_stuck_calls": {"queue": "io"},
        "worker.tasks.webitel.sync_webitel_calls": {"queue": "io"},
        "worker.tasks.webitel.sync_operators_from_webitel": {"queue": "io"},
        "worker.tasks.calls_export.run_calls_export": {"queue": "io"},
    },
)

celery_app.autodiscover_tasks(["worker.tasks"])


@worker_process_init.connect
def _setup_worker_logging(**kwargs):
    from app.core.logging import setup_logging

    setup_logging()


@task_prerun.connect
def _restore_trace_id(task=None, **kwargs):
    from app.core.context import set_trace_id

    headers = getattr(getattr(task, "request", None), "headers", None) or {}
    set_trace_id(str(headers.get("trace_id") or ""))


try:
    from celery.signals import worker_ready

    @worker_ready.connect
    def _clear_asr_slots_on_worker_start(sender=None, **kwargs):
        from worker.asr_limit import reset_asr_slots

        reset_asr_slots()
except Exception:
    pass

celery_app.conf.beat_schedule = {
    "webitel-sync-every-30-min": {
        "task": "worker.tasks.webitel.sync_webitel_calls",
        "schedule": crontab(minute="*/30"),
    },
    "process-pending-calls": {
        "task": "worker.tasks.pipeline.process_pending_batch",
        "schedule": crontab(minute="*/5"),
    },
    "recover-stuck-calls": {
        "task": "worker.tasks.pipeline.recover_stuck_calls",
        "schedule": crontab(minute="*/10"),
    },
}
