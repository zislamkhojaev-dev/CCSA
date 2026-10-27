"""Bounded audio uploads. Controllers pass UploadFile objects; bytes never exceed the configured cap."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings
from app.core.errors import AppError

_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".ogg", ".webm", ".m4a", ".flac"})
_GENERIC_MIME = frozenset({"", "application/octet-stream", "application/ogg"})


def _mime_allowed(content_type: str | None) -> bool:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in _GENERIC_MIME or mime.startswith("audio/"):
        return True
    return mime == "video/webm"


async def _read_limited(upload: UploadFile, max_bytes: int, chunk_bytes: int) -> bytes:
    buf = bytearray()
    while True:
        chunk = await upload.read(chunk_bytes)
        if not chunk:
            break
        if len(buf) + len(chunk) > max_bytes:
            raise AppError.invalid(f"Файл превышает лимит {max_bytes} байт")
        buf.extend(chunk)
    if not buf:
        raise AppError.invalid("Пустой файл")
    return bytes(buf)


async def read_bounded_uploads(
    files: list[UploadFile],
    *,
    max_files: int | None = None,
    max_bytes: int | None = None,
) -> list[tuple[str, bytes, str]]:
    settings = get_settings()
    file_limit = settings.upload_max_files if max_files is None else max_files
    byte_limit = settings.upload_max_bytes if max_bytes is None else max_bytes
    chunk_bytes = max(1, settings.upload_read_chunk_bytes)
    if not files:
        raise AppError.invalid("Файлы не переданы")
    if len(files) > file_limit:
        raise AppError.invalid(f"Слишком много файлов (макс. {file_limit})")
    payloads: list[tuple[str, bytes, str]] = []
    for upload in files:
        raw_name = upload.filename or ""
        name = Path(raw_name).name
        if not name or name in {".", ".."} or "\x00" in name:
            raise AppError.invalid("Некорректное имя файла")
        ext = Path(name).suffix.lower()
        if ext not in _AUDIO_EXTENSIONS:
            raise AppError.invalid("Неподдерживаемый тип файла. Разрешены: mp3, wav, ogg, webm, m4a, flac")
        if not _mime_allowed(upload.content_type):
            raise AppError.invalid("Некорректный тип содержимого")
        data = await _read_limited(upload, byte_limit, chunk_bytes)
        mime = (upload.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
        payloads.append((name, data, mime or "application/octet-stream"))
    return payloads
