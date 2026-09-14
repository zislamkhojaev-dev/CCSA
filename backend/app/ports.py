"""Anti-Corruption Layer ports. Adapters live in app.services / worker."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


class StoragePort(Protocol):
    def upload_bytes(
        self, data: bytes, prefix: str, filename: str, content_type: str = "audio/mpeg"
    ) -> str: ...

    def put_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str: ...

    def download_bytes(self, key: str) -> bytes: ...


class WebitelPort(Protocol):
    async def test_connection(self) -> bool: ...

    async def fetch_call_history(
        self,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        size: int = 100,
    ) -> list[dict[str, Any]]: ...

    async def download_recording(self, file_id: str) -> bytes: ...


class WebitelDbPort(Protocol):
    def test_connection(
        self, host: str, port: int, database: str, user: str, password: str
    ) -> tuple[bool, str]: ...

    def fetch_recent_calls(
        self, host: str, port: int, database: str, user: str, password: str, limit: int = 50
    ) -> list[dict]: ...


class SttPort(Protocol):
    def transcribe(
        self,
        storage_key: str,
        *,
        model: str | None = None,
        diarization_method: str | None = None,
        timeout_sec: float = 600,
    ) -> dict[str, Any]: ...


class EventBusPort(Protocol):
    def publish(self, channel: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, channel: str) -> Any: ...


class TaskDispatcherPort(Protocol):
    def send(self, task_name: str, *args: Any, **kwargs: Any) -> None: ...
