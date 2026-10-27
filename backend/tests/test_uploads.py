import pytest

from app.core.errors import AppError
from app.services.uploads import read_bounded_uploads


class FakeUpload:
    def __init__(self, name: str, data: bytes, content_type: str = "audio/mpeg"):
        self.filename = name
        self.content_type = content_type
        self._data = data
        self.reads = 0

    async def read(self, n: int = -1) -> bytes:
        self.reads += 1
        if not self._data:
            return b""
        if n is None or n < 0:
            n = len(self._data)
        chunk, self._data = self._data[:n], self._data[n:]
        return chunk


async def test_accepts_audio_within_limits():
    upload = FakeUpload("call.MP3", b"abc")
    payloads = await read_bounded_uploads([upload], max_files=2, max_bytes=10)
    assert payloads == [("call.MP3", b"abc", "audio/mpeg")]


async def test_rejects_too_many_files_before_reading():
    first = FakeUpload("a.mp3", b"a")
    second = FakeUpload("b.wav", b"b")
    with pytest.raises(AppError, match="Слишком много"):
        await read_bounded_uploads([first, second], max_files=1, max_bytes=10)
    assert first.reads == 0
    assert second.reads == 0


async def test_rejects_extension_and_mime_and_empty_and_oversize():
    with pytest.raises(AppError, match="Неподдерживаемый тип"):
        await read_bounded_uploads([FakeUpload("notes.txt", b"hi")], max_bytes=10)
    html = FakeUpload("a.mp3", b"hi", content_type="text/html")
    with pytest.raises(AppError, match="тип содержимого"):
        await read_bounded_uploads([html], max_bytes=10)
    assert html.reads == 0
    with pytest.raises(AppError, match="Пустой"):
        await read_bounded_uploads([FakeUpload("a.wav", b"")], max_bytes=10)
    with pytest.raises(AppError, match="превышает лимит"):
        await read_bounded_uploads([FakeUpload("a.ogg", b"12345")], max_bytes=4)
    nested = FakeUpload("../../secret.mp3", b"ok")
    payloads = await read_bounded_uploads([nested], max_bytes=10)
    assert payloads[0][0] == "secret.mp3"


async def test_allows_video_webm_and_generic_mime():
    webm = await read_bounded_uploads(
        [FakeUpload("a.webm", b"x", content_type="video/webm")], max_bytes=10
    )
    assert webm[0][2] == "video/webm"
    generic = await read_bounded_uploads(
        [FakeUpload("a.flac", b"x", content_type="application/octet-stream")], max_bytes=10
    )
    assert generic[0][0] == "a.flac"
