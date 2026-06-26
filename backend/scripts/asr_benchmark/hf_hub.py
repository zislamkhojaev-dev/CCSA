"""Hugging Face Hub env for fast downloads (benchmark + setup)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HF_CACHE = ROOT / "models" / "hf-cache"

# All benchmark models that download from HF on first use
BENCHMARK_HF_MODEL_IDS = (
    "OvozifyLabs/whisper-small-uz-v1",
    "Jonibek21/Zehnova-Uzbek-STT",
    # Wave 2 (see benchmark/MODELS.md) — prefetch before benchmark integration
    "Gearnode/qwen3-asr-uzbek-v2",
    "facebook/mms-1b-all",
)

ZEHNOVA_HF_ID = "Jonibek21/Zehnova-Uzbek-STT"
QWEN3_ASR_UZ_HF_ID = "Gearnode/qwen3-asr-uzbek-v2"
MMS_1B_ALL_HF_ID = "facebook/mms-1b-all"
WAVE2_HF_MODEL_IDS = (QWEN3_ASR_UZ_HF_ID, MMS_1B_ALL_HF_ID)
# Default wave-2 prefetch/run skips Qwen until ~4 GB download is done
WAVE2_MMS_ONLY_HF_MODEL_IDS = (MMS_1B_ALL_HF_ID,)


def _parse_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key.startswith("HF_") or key in ("HUGGINGFACE_HUB_TOKEN",):
            os.environ.setdefault(key, value)


def configure_hf_hub(*, cache_dir: Path | None = None) -> Path:
    """
    Load HF_* from project .env and apply fast-download defaults.

    Returns the effective HF hub cache directory.
    """
    _parse_env_file(ROOT / ".env")
    _parse_env_file(ROOT / "benchmark" / "hf.env")

    cache = cache_dir or Path(os.environ.get("HF_HUB_CACHE") or DEFAULT_HF_CACHE)
    cache.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_HUB_CACHE", str(cache))
    os.environ.setdefault("HF_HOME", str(cache.parent))

    # hf_transfer: parallel chunked downloads (pip install hf-transfer)
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "0")

    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")

    token = _normalize_hf_token(
        os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    )
    if token:
        os.environ["HF_TOKEN"] = token
        os.environ["HUGGINGFACE_HUB_TOKEN"] = token

    return cache


def _normalize_hf_token(raw: str | None) -> str | None:
    if not raw:
        return None
    token = raw.strip().strip('"').strip("'")
    if not token:
        return None
    if token.lower().startswith("hf_token="):
        token = token.split("=", 1)[1].strip()
    if not token.startswith("hf_"):
        raise ValueError(
            "HF_TOKEN must start with 'hf_'. "
            "Set in .env as: HF_TOKEN=hf_your_token (not the token alone on a line)."
        )
    return token


def hf_token_status() -> str:
    try:
        token = _normalize_hf_token(
            os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        )
    except ValueError as e:
        return str(e)
    if not token:
        return "not set (OK for public models)"
    return f"set ({token[:7]}…{token[-4:]})"


def hf_download_kwargs() -> dict:
    token = _normalize_hf_token(
        os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    )
    return {"token": token} if token else {}


def ensure_hf_transfer() -> bool:
    try:
        import hf_transfer  # noqa: F401

        return True
    except ImportError:
        return False
