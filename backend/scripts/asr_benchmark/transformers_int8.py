"""Prepare and load Ovozify transformers INT8 artifact for the ASR benchmark."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

QUANTIZATION_META = "quantization.json"
WEIGHTS_FILE = "pytorch_model_int8.bin"


def is_ready(path: str | Path) -> bool:
    root = Path(path)
    return (root / QUANTIZATION_META).is_file() and (root / WEIGHTS_FILE).is_file()


def _quantize_dynamic(model: object) -> object:
    import torch
    from torch.ao.quantization import quantize_dynamic

    supported = torch.backends.quantized.supported_engines
    if "qnnpack" in supported:
        torch.backends.quantized.engine = "qnnpack"
    elif "fbgemm" in supported:
        torch.backends.quantized.engine = "fbgemm"

    return quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)


def prepare_transformers_int8(
    hf_id: str,
    output_dir: str | Path,
    *,
    force: bool = False,
) -> str:
    """Download HF Whisper, dynamic-quantize Linear layers to int8, save artifact."""
    out = Path(output_dir)
    if is_ready(out) and not force:
        logger.info("Transformers INT8 artifact already exists at %s", out)
        return str(out)

    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    logger.info("Preparing transformers INT8 %s → %s", hf_id, out)
    processor = AutoProcessor.from_pretrained(hf_id)
    try:
        model = AutoModelForSpeechSeq2Seq.from_pretrained(hf_id, dtype=torch.float32)
    except TypeError:
        model = AutoModelForSpeechSeq2Seq.from_pretrained(hf_id, torch_dtype=torch.float32)
    model.eval()
    model = _quantize_dynamic(model)

    out.mkdir(parents=True, exist_ok=True)
    processor.save_pretrained(out)
    model.config.save_pretrained(out)
    torch.save(model.state_dict(), out / WEIGHTS_FILE)
    meta = {
        "method": "dynamic",
        "dtype": "qint8",
        "source_hf_id": hf_id,
        "layers": ["Linear"],
    }
    (out / QUANTIZATION_META).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if not is_ready(out):
        raise RuntimeError(f"Transformers INT8 artifact incomplete in {out}")
    return str(out)


def load_transformers_int8_pipeline(artifact_dir: str | Path) -> object:
    """Load ASR pipeline from a prepared transformers INT8 artifact."""
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    from scripts.asr_benchmark.transformers_pipe import build_whisper_pipeline

    out = Path(artifact_dir)
    if not is_ready(out):
        raise FileNotFoundError(f"Transformers INT8 artifact not found: {out}")

    meta = json.loads((out / QUANTIZATION_META).read_text(encoding="utf-8"))
    hf_id = meta["source_hf_id"]

    processor = AutoProcessor.from_pretrained(out)
    try:
        model = AutoModelForSpeechSeq2Seq.from_pretrained(hf_id, dtype=torch.float32)
    except TypeError:
        model = AutoModelForSpeechSeq2Seq.from_pretrained(hf_id, torch_dtype=torch.float32)
    model = _quantize_dynamic(model)
    state = torch.load(out / WEIGHTS_FILE, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()

    return build_whisper_pipeline(model, processor.tokenizer, processor.feature_extractor)
