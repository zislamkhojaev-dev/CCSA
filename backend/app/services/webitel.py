import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import get_settings
from app.core.errors import USER_ERROR_WEBITEL, AppError, ErrorCode
from app.core.logging import log_error
from app.core.retry import retry_async

logger = logging.getLogger(__name__)


class WebitelClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.webitel_api_url).rstrip("/")
        self.token = token or settings.webitel_access_token
        self._retries = settings.webitel_max_retries
        self._timeout_test = settings.webitel_timeout_sec
        self._timeout_list = settings.webitel_timeout_list_sec
        self._timeout_download = settings.webitel_timeout_download_sec

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def _get(self, url: str, *, timeout: float, params: dict[str, Any] | None = None) -> httpx.Response:
        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, headers=self._headers(), params=params)
                r.raise_for_status()
                return r

        return await retry_async(
            _once,
            retries=self._retries,
            exceptions=(httpx.HTTPError,),
            method="WebitelClient._get",
        )

    async def test_connection(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=self._timeout_test) as client:
                r = await client.get(
                    f"{self.base_url}/api/calls/history",
                    headers=self._headers(),
                    params={"size": 1},
                )
                return r.status_code < 500
        except Exception as e:
            log_error(logger, "Webitel connection test failed", method="test_connection", exc=e)
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
        try:
            r = await self._get(
                f"{self.base_url}/api/calls/history",
                timeout=self._timeout_list,
                params=params,
            )
        except httpx.HTTPError as e:
            log_error(
                logger,
                "Webitel fetch_call_history failed",
                method="fetch_call_history",
                params={"size": size},
                exc=e,
            )
            raise AppError(ErrorCode.EXT_WEBITEL_UNAVAILABLE, USER_ERROR_WEBITEL, 502) from e
        data = r.json()
        if isinstance(data, dict):
            return data.get("items") or data.get("data") or []
        return data if isinstance(data, list) else []

    async def download_recording(self, file_id: str) -> bytes:
        try:
            r = await self._get(
                f"{self.base_url}/api/storage/recordings/{file_id}/stream",
                timeout=self._timeout_download,
            )
            return r.content
        except httpx.HTTPError as e:
            log_error(
                logger,
                "Webitel download_recording failed",
                method="download_recording",
                params={"file_id": file_id},
                exc=e,
            )
            raise AppError(ErrorCode.EXT_WEBITEL_UNAVAILABLE, USER_ERROR_WEBITEL, 502) from e
