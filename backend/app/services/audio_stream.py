"""HTTP Range streaming of MinIO audio objects."""

from __future__ import annotations

import re
from collections.abc import Iterator

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from minio.error import S3Error

from app.services.storage import storage_service

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
_CHUNK = 64 * 1024


def _iter_object(resp, length: int | None = None) -> Iterator[bytes]:
    remaining = length
    try:
        while True:
            n = _CHUNK if remaining is None else min(_CHUNK, remaining)
            if n <= 0:
                break
            data = resp.read(n)
            if not data:
                break
            if remaining is not None:
                remaining -= len(data)
            yield data
    finally:
        resp.close()
        resp.release_conn()


def stream_audio(request: Request, key: str) -> StreamingResponse:
    try:
        size = storage_service.stat_size(key)
    except S3Error as e:
        raise HTTPException(status_code=404, detail="Audio not found") from e

    media = storage_service.media_type_for_key(key)
    range_header = request.headers.get("range")
    start, end = 0, size - 1
    status = 200
    if range_header:
        match = _RANGE_RE.fullmatch(range_header.strip())
        if not match:
            raise HTTPException(
                status_code=416,
                detail="Invalid Range",
                headers={"Content-Range": f"bytes */{size}"},
            )
        raw_start, raw_end = match.group(1), match.group(2)
        if raw_start:
            start = int(raw_start)
        if raw_end:
            end = int(raw_end)
        if start >= size or start > end:
            raise HTTPException(
                status_code=416,
                detail="Range not satisfiable",
                headers={"Content-Range": f"bytes */{size}"},
            )
        end = min(end, size - 1)
        status = 206

    length = end - start + 1 if size else 0
    resp = storage_service.open_object(key, offset=start, length=length if status == 206 else None)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "private, max-age=3600",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        _iter_object(resp, length),
        status_code=status,
        media_type=media,
        headers=headers,
    )
