from typing import Any

from app.services.redis_client import event_bus, get_redis


def publish_playground_event(job_id: int, payload: dict[str, Any]) -> None:
    event_bus.publish(f"playground:job:{job_id}", payload)


def publish_research_event(study_id: int, payload: dict[str, Any]) -> None:
    event_bus.publish(f"research:study:{study_id}", payload)


def publish_call_export_event(job_id: int, payload: dict[str, Any]) -> None:
    event_bus.publish(f"calls:export:{job_id}", payload)


def subscribe_playground_events(job_id: int):
    return event_bus.subscribe(f"playground:job:{job_id}")


def subscribe_research_events(study_id: int):
    return event_bus.subscribe(f"research:study:{study_id}")


def subscribe_call_export_events(job_id: int):
    return event_bus.subscribe(f"calls:export:{job_id}")


# Re-export for callers that imported get_redis from here.
__all__ = [
    "get_redis",
    "publish_playground_event",
    "publish_research_event",
    "publish_call_export_event",
    "subscribe_playground_events",
    "subscribe_research_events",
    "subscribe_call_export_events",
]
