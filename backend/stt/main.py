import logging
import os
import tempfile
import warnings
from io import BytesIO
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from stt.diarization import (
    DiarizationMethod,
    assign_speakers_to_utterances,
    assign_speakers_to_words,
    diarization_available,
    get_diarization_method,
    map_labels_to_roles,
    run_pyannote_diarization,
)
from stt.model_convert import DEFAULT_UZ_HF_ID, resolve_ct2_path
from stt.stereo_utils import merge_stereo_utterances, merge_stereo_words, split_stereo_to_channels
from stt.utterance_utils import (
    chunks_to_utterances,
    enforce_monotonic,
    finalize_utterances,
    group_words_to_utterances,
    merge_utterances,
    split_monologue,
    timestamps_degenerate,
)

logger = logging.getLogger(__name__)
app = FastAPI(title="CCSA STT Service", version="1.0.0")

_model: Any = None
_model_id: str | None = None
_engine: Literal["ct2", "transformers"] | None = None
_last_load_error: str | None = None

# UI keys → Hugging Face id (for display / conversion source)
ASR_MODEL_ALIASES: dict[str, str] = {
    "OvozifyLabs/whisper-small-uz-v1": DEFAULT_UZ_HF_ID,
    "Jonibek21/Zehnova-Uzbek-STT": "Jonibek21/Zehnova-Uzbek-STT",
    "zafarrr/uzbek-stt-fastconformer-v1.2": "Systran/faster-whisper-small",
}

CT2_MODEL_PREFIXES = ("Systran/faster-whisper",)
CT2_ELIGIBLE_HF_IDS = frozenset({DEFAULT_UZ_HF_ID})


class TranscribeRequest(BaseModel):
    storage_key: str
    model: str | None = None
    diarization_method: str | None = None


class TranscribeResponse(BaseModel):
    full_text: str
    utterances: list[dict]
    model_name: str
    channels: dict | None = None


def _resolve_model(model_name: str | None) -> tuple[str, Literal["ct2", "transformers"]]:
    resolved = model_name or os.getenv("STT_MODEL", DEFAULT_UZ_HF_ID)
    hf_id = ASR_MODEL_ALIASES.get(resolved, resolved)

    if hf_id in CT2_ELIGIBLE_HF_IDS or resolved in CT2_ELIGIBLE_HF_IDS:
        ct2_path = resolve_ct2_path(hf_id)
        if ct2_path:
            return ct2_path, "ct2"

    if hf_id.startswith(CT2_MODEL_PREFIXES):
        return hf_id, "ct2"

    return hf_id, "transformers"


def _get_model(model_name: str | None = None) -> tuple[Any, str, Literal["ct2", "transformers"]]:
    global _model, _model_id, _engine, _last_load_error
    hf_id, engine = _resolve_model(model_name)
    load_key = hf_id
    if _model is not None and _model_id == load_key and _engine == engine:
        return _model, hf_id, engine

    _model = None
    _last_load_error = None
    try:
        if engine == "ct2":
            from faster_whisper import WhisperModel

            device = os.getenv("STT_DEVICE", "cpu")
            compute_type = os.getenv("STT_COMPUTE_TYPE", "int8")
            logger.info("Loading faster-whisper (CT2) %s on %s (%s)", hf_id, device, compute_type)
            _model = WhisperModel(hf_id, device=device, compute_type=compute_type)
        else:
            import torch
            from transformers import pipeline

            device = os.getenv("STT_DEVICE", "cpu")
            if device == "cuda" and torch.cuda.is_available():
                torch_device: int | str = 0
            else:
                torch_device = "cpu"
            chunk_s = int(os.getenv("STT_CHUNK_LENGTH_S", "30"))
            stride_s = int(os.getenv("STT_STRIDE_LENGTH_S", "5"))
            logger.info("Loading transformers Whisper %s on %s", hf_id, torch_device)
            _model = pipeline(
                "automatic-speech-recognition",
                model=hf_id,
                device=torch_device,
                chunk_length_s=chunk_s,
                stride_length_s=stride_s,
            )
        _model_id = load_key
        _engine = engine
        return _model, hf_id, engine
    except Exception as e:
        _last_load_error = str(e)
        logger.exception("Could not load STT model %s (%s)", hf_id, engine)
        return None, hf_id, engine


def _download_audio(storage_key: str) -> bytes:
    from minio import Minio

    client = Minio(
        os.getenv("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "ccsa_minio"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "ccsa_minio_secret"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )
    bucket = os.getenv("MINIO_BUCKET", "ccsa-audio")
    response = client.get_object(bucket, storage_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _audio_duration_sec(path: str) -> float:
    try:
        from pydub import AudioSegment

        return len(AudioSegment.from_file(path)) / 1000.0
    except Exception:
        return 0.0


def _write_mono_wav(audio_bytes: bytes, path: str) -> None:
    from pydub import AudioSegment

    seg = AudioSegment.from_file(BytesIO(audio_bytes))
    mono = seg.set_channels(1) if seg.channels > 1 else seg
    mono.export(path, format="wav")


def _pad_audio_tail(path: str, padding_ms: int = 500) -> None:
    try:
        from pydub import AudioSegment

        seg = AudioSegment.from_file(path)
        padded = seg + AudioSegment.silent(duration=padding_ms)
        padded.export(path, format="wav")
    except Exception as e:
        logger.debug("Audio tail padding skipped: %s", e)


def _transcribe_transformers_clip(
    pipe: Any,
    path: str,
    speaker: str,
    base_offset: float,
    clip_duration: float,
) -> list[dict]:
    _pad_audio_tail(path)
    generate_kwargs = {"task": "transcribe", "num_beams": 1}
    tf_logger = logging.getLogger("transformers")
    prev_level = tf_logger.level

    try:
        tf_logger.setLevel(logging.ERROR)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Whisper did not predict an ending timestamp.*")
            warnings.filterwarnings("ignore", message=".*WhisperTimeStampLogitsProcessor.*")
            result = pipe(path, return_timestamps=True, generate_kwargs=generate_kwargs)
        chunks = result.get("chunks") or []
        if chunks:
            utterances = chunks_to_utterances(
                chunks,
                speaker=speaker,
                duration_sec=clip_duration,
                time_offset=base_offset,
            )
            if utterances and not timestamps_degenerate(utterances, clip_duration):
                return enforce_monotonic(utterances)
    except Exception as e:
        logger.warning("Whisper timestamps on clip failed: %s", e)
    finally:
        tf_logger.setLevel(prev_level)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = pipe(path, return_timestamps=False, generate_kwargs=generate_kwargs)
    text = (result.get("text") or "").strip()
    if not text:
        return []
    return split_monologue(
        text,
        speaker=speaker,
        duration_sec=clip_duration,
        time_offset=base_offset,
    )


def _transcribe_transformers_windowed(
    pipe: Any,
    path: str,
    speaker: str,
    time_offset: float,
) -> list[dict]:
    from pydub import AudioSegment

    seg = AudioSegment.from_file(path)
    window_ms = int(float(os.getenv("STT_WINDOW_S", "25")) * 1000)
    stride_ms = int(float(os.getenv("STT_WINDOW_STRIDE_S", "22")) * 1000)
    all_utterances: list[dict] = []

    for pos_ms in range(0, len(seg), stride_ms):
        piece = seg[pos_ms : pos_ms + window_ms]
        if len(piece) < 400:
            break
        clip_path = path + f".win{pos_ms}.wav"
        piece.export(clip_path, format="wav")
        clip_dur = len(piece) / 1000.0
        offset = pos_ms / 1000.0 + time_offset
        try:
            part = _transcribe_transformers_clip(pipe, clip_path, speaker, offset, clip_dur)
            all_utterances.extend(part)
        finally:
            try:
                os.unlink(clip_path)
            except OSError:
                pass

    return enforce_monotonic(all_utterances)


def _transcribe_transformers(pipe: Any, path: str, speaker: str, time_offset: float) -> list[dict]:
    duration_sec = _audio_duration_sec(path)
    if duration_sec <= 0:
        return []

    direct_max = float(os.getenv("STT_DIRECT_MAX_S", "45"))
    if duration_sec <= direct_max:
        utterances = _transcribe_transformers_clip(pipe, path, speaker, time_offset, duration_sec)
        if utterances and not timestamps_degenerate(utterances, duration_sec):
            return utterances

    logger.info("Windowed ASR for %.1fs (speaker=%s)", duration_sec, speaker)
    return _transcribe_transformers_windowed(pipe, path, speaker, time_offset)


def _ct2_language() -> str | None:
    lang = os.getenv("STT_LANGUAGE", "uz").strip()
    return lang or None


def _word_timestamps_enabled() -> bool:
    return os.getenv("STT_WORD_TIMESTAMPS", "true").lower() in ("1", "true", "yes")


def _ct2_temperature() -> float:
    raw = os.getenv("STT_TEMPERATURE", "0").strip().lower()
    if raw in ("fallback", "default", "auto"):
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _ct2_transcribe_kwargs(*, isolated_channel: bool = False) -> dict[str, Any]:
    lang = _ct2_language()
    if isolated_channel:
        vad = os.getenv("STT_CHANNEL_VAD_FILTER", "false").lower() in ("1", "true", "yes")
    else:
        vad = os.getenv("STT_VAD_FILTER", "true").lower() in ("1", "true", "yes")

    kwargs: dict[str, Any] = {
        "beam_size": int(os.getenv("STT_BEAM_SIZE", "5")),
        "vad_filter": vad,
        "condition_on_previous_text": False,
        "compression_ratio_threshold": float(os.getenv("STT_COMPRESSION_RATIO_THRESHOLD", "2.4")),
        "log_prob_threshold": float(os.getenv("STT_LOG_PROB_THRESHOLD", "-1.0")),
        "no_speech_threshold": float(os.getenv("STT_NO_SPEECH_THRESHOLD", "0.6")),
        "word_timestamps": _word_timestamps_enabled(),
        "temperature": _ct2_temperature(),
    }
    if lang:
        kwargs["language"] = lang
    return kwargs


def _words_from_ct2_segments(segments: Any, time_offset: float) -> list[dict]:
    words: list[dict] = []
    for seg in segments:
        seg_words = getattr(seg, "words", None)
        if seg_words:
            for w in seg_words:
                text = (getattr(w, "word", None) or "").strip()
                if not text:
                    continue
                start = float(getattr(w, "start", 0.0)) + time_offset
                end = float(getattr(w, "end", start)) + time_offset
                if end <= start:
                    end = start + 0.05
                words.append(
                    {
                        "text": text,
                        "start": round(start, 2),
                        "end": round(end, 2),
                    }
                )
            continue

        text = (getattr(seg, "text", None) or "").strip()
        if not text:
            continue
        start = float(getattr(seg, "start", 0.0)) + time_offset
        end = float(getattr(seg, "end", start)) + time_offset
        if end <= start:
            end = start + 0.2
        words.append(
            {
                "text": text,
                "start": round(start, 2),
                "end": round(end, 2),
            }
        )
    return words


def _transcribe_ct2_words(
    model: Any,
    path: str,
    time_offset: float = 0.0,
    *,
    isolated_channel: bool = False,
) -> list[dict]:
    kwargs = _ct2_transcribe_kwargs(isolated_channel=isolated_channel)
    kwargs["word_timestamps"] = True
    segments, _info = model.transcribe(path, **kwargs)
    return _words_from_ct2_segments(segments, time_offset)


def _transcribe_ct2_raw(
    model: Any,
    path: str,
    time_offset: float = 0.0,
    *,
    isolated_channel: bool = False,
) -> list[dict]:
    kwargs = _ct2_transcribe_kwargs(isolated_channel=isolated_channel)

    segments, _info = model.transcribe(path, **kwargs)
    utterances: list[dict] = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        no_speech = getattr(seg, "no_speech_prob", None)
        if no_speech is not None and no_speech > kwargs["no_speech_threshold"]:
            continue
        utterances.append(
            {
                "speaker": "mixed",
                "text": text,
                "start": round(seg.start + time_offset, 2),
                "end": round(seg.end + time_offset, 2),
            }
        )
    return utterances


def _transcribe_file(
    model: Any,
    path: str,
    speaker: str,
    engine: Literal["ct2", "transformers"],
    time_offset: float = 0.0,
    *,
    isolated_channel: bool = False,
) -> list[dict]:
    if engine == "ct2":
        utterances = _transcribe_ct2_raw(
            model, path, time_offset, isolated_channel=isolated_channel
        )
        for u in utterances:
            u["speaker"] = speaker
        return utterances

    return _transcribe_transformers(model, path, speaker, time_offset)


def _load_audio_segment(audio_bytes: bytes) -> Any:
    from pydub import AudioSegment

    return AudioSegment.from_file(BytesIO(audio_bytes))


def _split_stereo(audio_bytes: bytes) -> tuple[bytes | None, bytes | None]:
    """Split stereo into client/agent mono WAV bytes (see STT_CLIENT_CHANNEL)."""
    try:
        client_bytes, agent_bytes, mapping = split_stereo_to_channels(audio_bytes)
        if not client_bytes or not agent_bytes:
            logger.info("Stereo split skipped (%s)", mapping)
            return None, None
        logger.info("Stereo split OK: %s", mapping)
        return client_bytes, agent_bytes
    except Exception as e:
        logger.warning("Stereo split failed: %s", e)
        return None, None


def _channel_summary(utterances: list[dict], path: str) -> dict:
    return {
        "utterance_count": len(utterances),
        "duration_sec": round(_audio_duration_sec(path), 2),
    }


def _transcribe_stereo_channels(
    model: Any,
    engine: Literal["ct2", "transformers"],
    client_bytes: bytes,
    agent_bytes: bytes,
    tmpdir: str,
) -> tuple[list[dict], dict]:
    client_path = os.path.join(tmpdir, "client.wav")
    agent_path = os.path.join(tmpdir, "agent.wav")
    with open(client_path, "wb") as f:
        f.write(client_bytes)
    with open(agent_path, "wb") as f:
        f.write(agent_bytes)

    use_word_merge = engine == "ct2" and _word_timestamps_enabled()
    if use_word_merge:
        client_words = _transcribe_ct2_words(
            model, client_path, 0.0, isolated_channel=True
        )
        agent_words = _transcribe_ct2_words(
            model, agent_path, 0.0, isolated_channel=True
        )
        merged = merge_stereo_words(client_words, agent_words, client_path, agent_path)
        client_u = [u for u in merged if u["speaker"] == "client"]
        agent_u = [u for u in merged if u["speaker"] == "agent"]
    else:
        client_u = _transcribe_file(
            model, client_path, "client", engine, 0.0, isolated_channel=True
        )
        agent_u = _transcribe_file(
            model, agent_path, "agent", engine, 0.0, isolated_channel=True
        )
        merged = merge_stereo_utterances(client_u, agent_u, client_path, agent_path)
        merged = merge_stereo_utterances(client_u, agent_u, client_path, agent_path)

    mapping = os.getenv("STT_CLIENT_CHANNEL", "left")
    mapping = (
        "left=client, right=agent"
        if mapping.strip().lower() != "right"
        else "right=client, left=agent"
    )
    meta = {
        "mode": "stereo",
        "diarization": "stereo_channels",
        "word_level": use_word_merge,
        "mapping": mapping,
        "client": _channel_summary(client_u, client_path),
        "agent": _channel_summary(agent_u, agent_path),
        "merged_utterances": len(merged),
    }
    return merged, meta


def _transcribe_pyannote(
    model: Any,
    engine: Literal["ct2", "transformers"],
    audio_bytes: bytes,
    tmpdir: str,
    *,
    client_bytes: bytes | None = None,
    agent_bytes: bytes | None = None,
) -> tuple[list[dict], dict]:
    mono_path = os.path.join(tmpdir, "mono.wav")
    _write_mono_wav(audio_bytes, mono_path)

    client_path: str | None = None
    agent_path: str | None = None
    if client_bytes and agent_bytes:
        client_path = os.path.join(tmpdir, "client.wav")
        agent_path = os.path.join(tmpdir, "agent.wav")
        with open(client_path, "wb") as f:
            f.write(client_bytes)
        with open(agent_path, "wb") as f:
            f.write(agent_bytes)

    diar_segments = run_pyannote_diarization(mono_path)
    label_map = map_labels_to_roles(
        diar_segments,
        stereo_client_path=client_path,
        stereo_agent_path=agent_path,
    )

    if engine == "ct2" and _word_timestamps_enabled():
        words = _transcribe_ct2_words(model, mono_path, 0.0)
        if words:
            labeled = assign_speakers_to_words(words, diar_segments, label_map)
            utterances = group_words_to_utterances(labeled)
        else:
            raw = _transcribe_ct2_raw(model, mono_path, 0.0)
            utterances = assign_speakers_to_utterances(raw, diar_segments, label_map)
    elif engine == "ct2":
        raw = _transcribe_ct2_raw(model, mono_path, 0.0)
        utterances = assign_speakers_to_utterances(raw, diar_segments, label_map)
    else:
        raw = _transcribe_transformers(model, mono_path, "mixed", 0.0)
        utterances = assign_speakers_to_utterances(raw, diar_segments, label_map)

    meta = {
        "mode": "mono" if not client_bytes else "stereo",
        "diarization": "pyannote",
        "word_level": engine == "ct2" and _word_timestamps_enabled(),
        "diarization_segments": len(diar_segments),
        "speaker_labels": label_map,
        "asr_passes": 1,
        "mixed": _channel_summary(utterances, mono_path),
    }
    return utterances, meta


def _run_transcription(
    model: Any,
    model_name: str,
    engine: Literal["ct2", "transformers"],
    audio_bytes: bytes,
    method: DiarizationMethod,
) -> tuple[list[dict], dict]:
    client_bytes, agent_bytes = _split_stereo(audio_bytes)

    with tempfile.TemporaryDirectory() as tmpdir:
        if method == "stereo_channels" and client_bytes and agent_bytes:
            utterances, meta = _transcribe_stereo_channels(
                model, engine, client_bytes, agent_bytes, tmpdir
            )
            logger.info(
                "Stereo-channel ASR: client=%s agent=%s merged=%s",
                meta["client"]["utterance_count"],
                meta["agent"]["utterance_count"],
                len(utterances),
            )
            return utterances, meta

        if method == "pyannote":
            if not diarization_available():
                logger.warning("HF_TOKEN missing — falling back from pyannote")
            else:
                try:
                    utterances, meta = _transcribe_pyannote(
                        model,
                        engine,
                        audio_bytes,
                        tmpdir,
                        client_bytes=client_bytes,
                        agent_bytes=agent_bytes,
                    )
                    logger.info(
                        "Pyannote diarization + single ASR: %s segments, %s utterances",
                        meta.get("diarization_segments"),
                        len(utterances),
                    )
                    return utterances, meta
                except Exception as e:
                    logger.warning("Pyannote diarization failed, fallback: %s", e)

            if client_bytes and agent_bytes:
                return _transcribe_stereo_channels(
                    model, engine, client_bytes, agent_bytes, tmpdir
                )

        mono_path = os.path.join(tmpdir, "mono.wav")
        _write_mono_wav(audio_bytes, mono_path)
        utterances = _transcribe_file(model, mono_path, "mixed", engine, 0.0)
        meta = {
            "mode": "mono",
            "diarization": method if method == "mono" else "mono_fallback",
            "mapping": None,
            "mixed": _channel_summary(utterances, mono_path),
        }
        return utterances, meta


def _cache_stats() -> dict[str, Any]:
    cache_root = os.getenv("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    hub = os.path.join(cache_root, "hub")
    total_bytes = 0
    model_dirs: list[str] = []
    if os.path.isdir(hub):
        for name in os.listdir(hub):
            path = os.path.join(hub, name)
            if os.path.isdir(path):
                model_dirs.append(name)
                for root, _dirs, files in os.walk(path):
                    for f in files:
                        try:
                            total_bytes += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass
    return {
        "cache_path": hub,
        "cached_models": model_dirs,
        "cache_size_mb": round(total_bytes / (1024 * 1024), 1),
    }


@app.get("/health")
def health():
    hf_id, engine = _resolve_model(None)
    method = get_diarization_method(None)
    return {
        "status": "ok" if _model is not None or _last_load_error is None else "degraded",
        "model_loaded": _model is not None,
        "model_id": _model_id or hf_id,
        "engine": _engine or engine,
        "configured_model": os.getenv("STT_MODEL", DEFAULT_UZ_HF_ID),
        "diarization_method": method,
        "pyannote_available": diarization_available(),
        "load_error": _last_load_error,
        **_cache_stats(),
    }


@app.post("/transcribe", response_model=TranscribeResponse)
def transcribe(req: TranscribeRequest):
    audio_bytes = _download_audio(req.storage_key)
    model, model_name, engine = _get_model(req.model)

    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"STT model not loaded ({model_name}, engine={engine}): {_last_load_error}",
        )

    method = get_diarization_method(req.diarization_method)
    all_utterances, channels_meta = _run_transcription(
        model, model_name, engine, audio_bytes, method
    )

    all_utterances = finalize_utterances(all_utterances)
    full_text = " ".join(u["text"] for u in all_utterances)
    return TranscribeResponse(
        full_text=full_text,
        utterances=all_utterances,
        model_name=f"{model_name} ({engine})",
        channels=channels_meta or None,
    )
