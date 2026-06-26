#!/usr/bin/env python3
"""Run ASR benchmark: local models only, WER/CER vs baseline, latency, RSS."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

warnings.filterwarnings("ignore", message=".*OpenSSL.*urllib3.*")
warnings.filterwarnings("ignore", message=".*chunk_length_s.*experimental.*")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.asr_benchmark.hf_hub import configure_hf_hub  # noqa: E402

configure_hf_hub()

from scripts.asr_benchmark.config import (  # noqa: E402
    BASELINE_SLUG,
    discover_audio_files,
    missing_artifacts,
    model_specs,
    output_run_dir,
)
from scripts.asr_benchmark.metrics import cer, wer  # noqa: E402
from scripts.asr_benchmark.transcribers import ModelRunner  # noqa: E402


@dataclass
class RunRow:
    model_slug: str
    model_label: str
    audio_file: str
    duration_sec: float
    peak_rss_mb: float
    wer_vs_baseline: float | None = None
    cer_vs_baseline: float | None = None
    transcript_path: str = ""


def _rss_mb(rss_bytes: int) -> float:
    return round(rss_bytes / (1024 * 1024), 2)


def _seed_baseline_transcripts(out_dir: Path, baseline_from: Path) -> None:
    src = baseline_from / "transcripts" / BASELINE_SLUG
    dst = out_dir / "transcripts" / BASELINE_SLUG
    if not src.is_dir():
        raise SystemExit(
            f"Baseline transcripts not found: {src}\n"
            f"Use a full benchmark run dir (e.g. benchmark/results/20260521_100914)"
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"Baseline transcripts copied from {baseline_from}")


def _validate_prerequisites(*, check_audio: bool = True, wave1_artifacts: bool = True) -> list[Path]:
    missing = missing_artifacts(wave1_only=wave1_artifacts)
    if missing:
        raise SystemExit(
            "Missing model artifacts:\n  "
            + "\n  ".join(missing)
            + "\nRun: make benchmark-setup"
        )

    if not check_audio:
        return []

    audio_files = discover_audio_files()
    if not audio_files:
        raise SystemExit(
            "No audio files found. Place mono files as benchmark/audio/1.wav … 6.wav"
        )
    return audio_files


def _save_transcript(out_dir: Path, model_slug: str, audio_stem: str, text: str) -> Path:
    target_dir = out_dir / "transcripts" / model_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{audio_stem}.txt"
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return path


def _run_all_models(
    specs,
    audio_files: list[Path],
    out_dir: Path,
    *,
    models_filter: set[str] | None,
) -> tuple[list[RunRow], dict[str, dict[str, str]]]:
    rows: list[RunRow] = []
    transcripts: dict[str, dict[str, str]] = {}

    for spec in specs:
        if models_filter and spec.slug not in models_filter:
            continue

        print(f"\n=== {spec.label} ===")
        runner = ModelRunner(spec)
        try:
            runner.load()
            for audio in audio_files:
                stem = audio.stem
                print(f"  {audio.name} ...", end=" ", flush=True)
                result = runner.transcribe_file(str(audio))
                rel_path = _save_transcript(out_dir, spec.slug, stem, result.text)
                transcripts.setdefault(spec.slug, {})[stem] = result.text
                rows.append(
                    RunRow(
                        model_slug=spec.slug,
                        model_label=spec.label,
                        audio_file=audio.name,
                        duration_sec=round(result.duration_sec, 3),
                        peak_rss_mb=_rss_mb(runner.session_peak_rss),
                        transcript_path=str(rel_path.relative_to(out_dir)),
                    )
                )
                print(
                    f"{result.duration_sec:.1f}s, "
                    f"RSS {_rss_mb(runner.session_peak_rss)} MB (session peak)"
                )
        finally:
            runner.unload()

    return rows, transcripts


def _attach_quality_metrics(rows: list[RunRow], transcripts: dict[str, dict[str, str]]) -> None:
    baseline = transcripts.get(BASELINE_SLUG, {})
    if not baseline:
        print(f"\nWarning: baseline '{BASELINE_SLUG}' missing; WER/CER will be empty")

    for row in rows:
        if row.model_slug == BASELINE_SLUG:
            continue
        stem = Path(row.audio_file).stem
        hyp = transcripts.get(row.model_slug, {}).get(stem, "")
        ref = baseline.get(stem, "")
        if ref:
            row.wer_vs_baseline = round(wer(ref, hyp), 4)
            row.cer_vs_baseline = round(cer(ref, hyp), 4)


def _aggregate(rows: list[RunRow]) -> dict[str, dict]:
    by_model: dict[str, list[RunRow]] = {}
    for row in rows:
        by_model.setdefault(row.model_slug, []).append(row)

    summary: dict[str, dict] = {}
    for slug, model_rows in by_model.items():
        summary[slug] = {
            "model_label": model_rows[0].model_label,
            "is_baseline": slug == BASELINE_SLUG,
            "files": len(model_rows),
            "total_duration_sec": round(sum(r.duration_sec for r in model_rows), 3),
            "avg_duration_sec": round(
                sum(r.duration_sec for r in model_rows) / len(model_rows), 3
            ),
            "peak_rss_mb_max": max(r.peak_rss_mb for r in model_rows),
            "avg_wer_vs_baseline": _avg([r.wer_vs_baseline for r in model_rows]),
            "avg_cer_vs_baseline": _avg([r.cer_vs_baseline for r in model_rows]),
        }
    return summary


def _avg(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 4)


def _hypotheses(summary: dict[str, dict]) -> list[dict]:
    """Check Ovozify ablation hypotheses vs ovozify-transformers-fp32 baseline."""
    base_wer = summary.get(BASELINE_SLUG, {}).get("avg_wer_vs_baseline")
    if base_wer is None:
        base_wer = 0.0

    checks = [
        {
            "id": "H1",
            "description": "transformers int8 не хуже fp32 более чем на 5 п.п. WER",
            "baseline": BASELINE_SLUG,
            "candidate": "ovozify-transformers-int8",
            "max_delta": 0.05,
        },
        {
            "id": "H2",
            "description": "CT2 fp32 не хуже transformers fp32",
            "baseline": BASELINE_SLUG,
            "candidate": "ovozify-ct2-fp32",
            "max_delta": 0.0,
        },
        {
            "id": "H3",
            "description": "CT2 int8 не хуже исходной transformers fp32",
            "baseline": BASELINE_SLUG,
            "candidate": "ovozify-ct2-int8",
            "max_delta": 0.0,
        },
    ]

    out: list[dict] = []
    for check in checks:
        cand_wer = summary.get(check["candidate"], {}).get("avg_wer_vs_baseline")
        if cand_wer is None:
            out.append({**check, "passed": None, "note": "insufficient data"})
            continue
        delta = round(cand_wer - base_wer, 4)
        passed = delta <= check["max_delta"]
        out.append(
            {
                **check,
                "baseline_avg_wer": base_wer,
                "candidate_avg_wer": cand_wer,
                "delta": delta,
                "passed": passed,
            }
        )
    return out


def _write_csv(path: Path, rows: list[RunRow]) -> None:
    fieldnames = list(asdict(rows[0]).keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> None:
    parser = argparse.ArgumentParser(description="ASR benchmark for CCSA (local models)")
    parser.add_argument("--audio-dir", type=Path, default=None, help="Override benchmark/audio")
    parser.add_argument("--output", type=Path, default=None, help="Output directory")
    parser.add_argument(
        "--models",
        nargs="*",
        help="Run only these model slugs (default: all local)",
    )
    parser.add_argument(
        "--check-artifacts-only",
        action="store_true",
        help="Verify model artifacts and exit (no audio required)",
    )
    parser.add_argument(
        "--wave2-only",
        action="store_true",
        help="Run wave-2 without Qwen: mms-1b-all-uz only",
    )
    parser.add_argument(
        "--include-qwen",
        action="store_true",
        help="With --wave2-only: also run qwen3-asr-uzbek-v2 (needs .venv-benchmark311)",
    )
    parser.add_argument(
        "--baseline-from",
        type=Path,
        default=None,
        help="Copy baseline transcripts from another run dir for WER (wave-2 runs)",
    )
    args = parser.parse_args()

    wave1_artifacts = not args.wave2_only

    if args.check_artifacts_only:
        missing = missing_artifacts(wave1_only=wave1_artifacts)
        if missing:
            raise SystemExit("Missing artifacts:\n  " + "\n  ".join(missing))
        print("All benchmark artifacts are ready.")
        return

    if args.audio_dir:
        missing = missing_artifacts(wave1_only=wave1_artifacts)
        if missing:
            raise SystemExit(
                "Missing model artifacts:\n  "
                + "\n  ".join(missing)
                + "\nRun: make benchmark-setup"
            )
        audio_files = discover_audio_files(args.audio_dir)
        if not audio_files:
            raise SystemExit(f"No audio in {args.audio_dir}")
    else:
        audio_files = _validate_prerequisites(wave1_artifacts=wave1_artifacts)

    out_dir = args.output or output_run_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = model_specs(wave2_only=args.wave2_only, include_qwen=args.include_qwen)
    models_filter = set(args.models) if args.models else None

    print(f"Audio files: {[p.name for p in audio_files]}")
    print(f"Output: {out_dir}")
    print(f"Baseline: {BASELINE_SLUG}")
    wave2_label = "wave 2 (MMS only)" if args.wave2_only and not args.include_qwen else (
        "wave 2 (+ Qwen)" if args.wave2_only else "all"
    )
    print(f"Models: {len(specs)} ({wave2_label})")
    if args.wave2_only and not args.include_qwen:
        print("Skipping qwen3-asr-uzbek-v2 (pass --include-qwen to enable)")

    rows, transcripts = _run_all_models(
        specs,
        audio_files,
        out_dir,
        models_filter=models_filter,
    )

    if args.baseline_from:
        _seed_baseline_transcripts(out_dir, args.baseline_from.resolve())
        baseline_dir = out_dir / "transcripts" / BASELINE_SLUG
        for txt in sorted(baseline_dir.glob("*.txt")):
            transcripts.setdefault(BASELINE_SLUG, {})[txt.stem] = txt.read_text(
                encoding="utf-8"
            ).strip()

    _attach_quality_metrics(rows, transcripts)

    summary = _aggregate(rows)
    hypotheses = _hypotheses(summary)

    payload = {
        "baseline_slug": BASELINE_SLUG,
        "audio_files": [p.name for p in audio_files],
        "rows": [asdict(r) for r in rows],
        "summary_by_model": summary,
        "hypotheses": hypotheses,
    }

    json_path = out_dir / "results.json"
    csv_path = out_dir / "results.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        _write_csv(csv_path, rows)

    print(f"\nSaved {json_path}")
    print(f"Saved {csv_path}")
    print(f"\n--- Summary (avg WER vs {BASELINE_SLUG}) ---")
    for slug, data in summary.items():
        wer_b = data.get("avg_wer_vs_baseline")
        if data.get("is_baseline"):
            wer_str = "baseline"
        elif wer_b is not None:
            wer_str = f"{wer_b:.2%}"
        else:
            wer_str = "n/a"
        print(
            f"  {slug}: WER={wer_str}, "
            f"avg {data['avg_duration_sec']}s, RSS {data['peak_rss_mb_max']} MB"
        )

    if hypotheses:
        print("\n--- Hypotheses ---")
        for h in hypotheses:
            status = "PASS" if h.get("passed") else ("FAIL" if h.get("passed") is False else "N/A")
            print(f"  {h['id']}: {status} — {h['description']}")
            if "delta" in h:
                print(f"       delta WER={h['delta']:+.2%}")


if __name__ == "__main__":
    main()
