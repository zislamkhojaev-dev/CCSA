"""STT HTTP adapter (Anti-Corruption Layer)."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.core.logging import log_error
import logging

logger = logging.getLogger(__name__)


class SttClient:
    def transcribe(
        self,
        storage_key: str,
        *,
        model: str | None = None,
        diarization_method: str | None = None,
        timeout_sec: float = 600,
    ) -> dict[str, Any]:
        settings = get_settings()
        payload: dict[str, Any] = {"storage_key": storage_key}
        if model:
            payload["model"] = model
        if diarization_method:
            payload["diarization_method"] = diarization_method
        headers: dict[str, str] = {}
        if settings.stt_service_token:
            headers["X-STT-Token"] = settings.stt_service_token
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                r = client.post(
                    f"{settings.stt_service_url}/transcribe",
                    json=payload,
                    headers=headers,
                )
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError as exc:
            log_error(
                logger,
                "STT transcribe failed",
                method="SttClient.transcribe",
                params={"storage_key": storage_key},
                exc=exc,
            )
            raise


stt_client = SttClient()
