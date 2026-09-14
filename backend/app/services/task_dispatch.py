"""Celery dispatcher so API modules do not import task implementations."""

from __future__ import annotations

from typing import Any

from app.core.context import get_trace_id


class TaskDispatcher:
    def send(self, task_name: str, *args: Any, **kwargs: Any) -> None:
        from worker.celery_app import celery_app

        celery_app.send_task(
            task_name,
            args=args,
            kwargs=kwargs,
            headers={"trace_id": get_trace_id()},
        )

    def reanalyze_call(self, call_id: int, scenario_id: int | None = None) -> None:
        self.send("worker.tasks.pipeline.reanalyze_call", call_id, scenario_id)

    def retranscribe_call(self, call_id: int) -> None:
        self.send("worker.tasks.pipeline.retranscribe_call", call_id)

    def run_calls_export(self, job_id: int) -> None:
        self.send("worker.tasks.calls_export.run_calls_export", job_id)

    def run_research_study(self, study_id: int) -> None:
        self.send("worker.tasks.research.run_research_study", study_id)

    def process_playground_file(self, file_id: int) -> None:
        self.send("worker.tasks.playground.process_playground_file", file_id)

    def backfill_topics(self) -> None:
        self.send("worker.tasks.pipeline.backfill_topics")

    def recover_stuck_calls(self, stale_minutes: int = 0) -> None:
        self.send("worker.tasks.pipeline.recover_stuck_calls", stale_minutes)


task_dispatcher = TaskDispatcher()
