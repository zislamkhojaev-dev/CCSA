import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class WebitelClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.webitel_api_url).rstrip("/")
        self.token = token or settings.webitel_access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def test_connection(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(f"{self.base_url}/api/calls/history", headers=self._headers(), params={"size": 1})
                return r.status_code < 500
        except Exception as e:
            logger.warning("Webitel connection test failed: %s", e)
            return False

    async def fetch_call_history(
        self,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        size: int = 100,
    ) -> list[dict[str, Any]]:
        if not self.base_url:
            return []
        created_from = created_from or datetime.utcnow() - timedelta(hours=24)
        created_to = created_to or datetime.utcnow()
        params = {
            "created_at_from": int(created_from.timestamp() * 1000),
            "created_at_to": int(created_to.timestamp() * 1000),
            "size": size,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{self.base_url}/api/calls/history",
                headers=self._headers(),
                params=params,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                return data.get("items") or data.get("data") or []
            return data if isinstance(data, list) else []

    async def download_recording(self, file_id: str) -> bytes:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(
                f"{self.base_url}/api/storage/recordings/{file_id}/stream",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.content
