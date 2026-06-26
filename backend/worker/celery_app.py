import os

from celery import Celery
from celery.schedules import crontab

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
)

celery_app.autodiscover_tasks(["worker.tasks"])


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
}
