"""Convert Hugging Face Whisper checkpoints to faster-whisper (CTranslate2) INT8."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_UZ_HF_ID = "OvozifyLabs/whisper-small-uz-v1"
TOKENIZER_FILES = ("tokenizer.json", "preprocessor_config.json")


def ct2_output_dir(hf_id: str, base: str | None = None) -> str:
    root = base or os.getenv("STT_CT2_CACHE_DIR", "/app/models")
    safe = hf_id.replace("/", "--")
    return os.path.join(root, f"{safe}-int8")


def is_ct2_model_dir(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "model.bin"))


def convert_hf_whisper_to_ct2(
    hf_id: str,
    output_dir: str,
    *,
    quantization: str = "int8",
    force: bool = False,
) -> str:
    """Download HF Whisper and export to faster-whisper layout."""
    out = Path(output_dir)
    if is_ct2_model_dir(str(out)) and not force:
        logger.info("CT2 model already exists at %s", out)
        return str(out)

    from ctranslate2.converters import TransformersConverter

    out.mkdir(parents=True, exist_ok=True)
    logger.info("Converting %s → %s (%s)", hf_id, out, quantization)

    copy_files = list(TOKENIZER_FILES)
    converter = TransformersConverter(model_name_or_path=hf_id, copy_files=copy_files)
    try:
        converter.convert(
            output_dir=str(out),
            quantization=quantization,
            force=True,
        )
    except Exception:
        logger.warning("Retrying conversion without explicit copy_files for %s", hf_id)
        converter = TransformersConverter(model_name_or_path=hf_id)
        converter.convert(
            output_dir=str(out),
            quantization=quantization,
            force=True,
        )

    if not is_ct2_model_dir(str(out)):
        raise RuntimeError(f"Conversion finished but model.bin missing in {out}")
    return str(out)


def resolve_ct2_path(hf_id: str) -> str | None:
    """Return local CT2 directory for a HF id, converting on demand if allowed."""
    explicit = os.getenv("STT_CT2_UZ_MODEL_PATH")
    if hf_id == DEFAULT_UZ_HF_ID and explicit and is_ct2_model_dir(explicit):
        return explicit

    path = ct2_output_dir(hf_id)
    if is_ct2_model_dir(path):
        return path

    if os.getenv("STT_AUTO_CONVERT_CT2", "true").lower() not in ("1", "true", "yes"):
        return None

    try:
        return convert_hf_whisper_to_ct2(hf_id, path)
    except Exception:
        logger.exception("On-demand CT2 conversion failed for %s", hf_id)
        return None
