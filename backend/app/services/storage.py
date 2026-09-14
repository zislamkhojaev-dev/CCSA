import io
import logging
import uuid
from datetime import timedelta

from minio import Minio

from app.config import get_settings
from app.core.errors import USER_ERROR_STORAGE, AppError, ErrorCode
from app.core.logging import log_error

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self) -> None:
        self._client: Minio | None = None
        self._bucket: str | None = None

    def _ensure_client(self) -> Minio:
        if self._client is None:
            settings = get_settings()
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            self._bucket = settings.minio_bucket
            self._ensure_bucket()
        return self._client

    @property
    def bucket(self) -> str:
        self._ensure_client()
        assert self._bucket is not None
        return self._bucket

    @property
    def client(self) -> Minio:
        return self._ensure_client()

    def _ensure_bucket(self) -> None:
        if self._client is None:
            return
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    def upload_bytes(self, data: bytes, prefix: str, filename: str, content_type: str = "audio/mpeg") -> str:
        key = f"{prefix}/{uuid.uuid4().hex}_{filename}"
        self.put_bytes(key, data, content_type=content_type)
        return key

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        try:
            self.client.put_object(
                self.bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return key
        except Exception as e:
            log_error(logger, "Storage put failed", method="put_bytes", params={"key": key}, exc=e)
            raise AppError(ErrorCode.EXT_STORAGE_UNAVAILABLE, USER_ERROR_STORAGE, 502) from e

    def download_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except AppError:
            raise
        except Exception as e:
            log_error(logger, "Storage download failed", method="download_bytes", params={"key": key}, exc=e)
            raise AppError(ErrorCode.EXT_STORAGE_UNAVAILABLE, USER_ERROR_STORAGE, 502) from e

    def stat_size(self, key: str) -> int:
        return int(self.client.stat_object(self.bucket, key).size)

    def open_object(self, key: str, offset: int = 0, length: int | None = None):
        kwargs: dict = {}
        if offset:
            kwargs["offset"] = offset
        if length is not None:
            kwargs["length"] = length
        return self.client.get_object(self.bucket, key, **kwargs)

    def get_presigned_url(self, key: str, expires_hours: int = 4) -> str:
        return self.client.presigned_get_object(
            self.bucket, key, expires=timedelta(hours=expires_hours)
        )

    @staticmethod
    def media_type_for_key(key: str) -> str:
        lower = key.lower()
        if lower.endswith(".wav"):
            return "audio/wav"
        if lower.endswith(".ogg"):
            return "audio/ogg"
        if lower.endswith(".webm"):
            return "audio/webm"
        return "audio/mpeg"


storage_service = StorageService()
