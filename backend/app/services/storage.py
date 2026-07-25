import io
import uuid
from datetime import timedelta

from minio import Minio

from app.config import get_settings


class StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_bytes(self, data: bytes, prefix: str, filename: str, content_type: str = "audio/mpeg") -> str:
        key = f"{prefix}/{uuid.uuid4().hex}_{filename}"
        self.put_bytes(key, data, content_type=content_type)
        return key

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload bytes to an exact object key (no random prefix)."""
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return key

    def download_bytes(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

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
