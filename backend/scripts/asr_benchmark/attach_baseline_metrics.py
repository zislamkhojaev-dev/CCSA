#!/usr/bin/env python3
"""Recompute WER/CER vs fp32 baseline from saved transcripts (no re-transcription)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.asr_benchmark.hf_hub import configure_hf_hub  # noqa: E402

configure_hf_hub()

from scripts.asr_benchmark.config import BASELINE_SLUG  # noqa: E402
from scripts.asr_benchmark.run_benchmark import (  # noqa: E402
    RunRow,
    _aggregate,
    _attach_quality_metrics,
    _hypotheses,
    _write_csv,
)


def _load_transcripts(run_dir: Path) -> dict[str, dict[str, str]]:
    transcripts: dict[str, dict[str, str]] = {}
    base = run_dir / "transcripts"
    if not base.is_dir():
        raise FileNotFoundError(f"No transcripts/ in {run_dir}")
    for model_dir in sorted(base.iterdir()):
        if not model_dir.is_dir():
            continue
        slug = model_dir.name
        transcripts[slug] = {}
        for txt in sorted(model_dir.glob("*.txt")):
            transcripts[slug][txt.stem] = txt.read_text(encoding="utf-8").strip()
    return transcripts


def _row_from_dict(d: dict) -> RunRow:
    return RunRow(
        model_slug=d["model_slug"],
        model_label=d["model_label"],
        audio_file=d["audio_file"],
        duration_sec=float(d["duration_sec"]),
        peak_rss_mb=float(d["peak_rss_mb"]),
        wer_vs_baseline=d.get("wer_vs_baseline"),
        cer_vs_baseline=d.get("cer_vs_baseline"),
        transcript_path=d.get("transcript_path", ""),
    )


def recompute(run_dir: Path) -> dict:
    json_path = run_dir / "results.json"
    if not json_path.is_file():
        raise FileNotFoundError(f"Missing {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    rows = [_row_from_dict(r) for r in payload.get("rows", [])]
    if not rows:
        raise SystemExit(f"No rows in {json_path}")

    transcripts = _load_transcripts(run_dir)
    if BASELINE_SLUG not in transcripts:
        raise SystemExit(
            f"Baseline transcripts missing: {run_dir / 'transcripts' / BASELINE_SLUG}"
        )

    for row in rows:
        row.wer_vs_baseline = None
        row.cer_vs_baseline = None

    _attach_quality_metrics(rows, transcripts)

    summary = _aggregate(rows)
    for slug, data in summary.items():
        data["is_baseline"] = slug == BASELINE_SLUG

    hypotheses = _hypotheses(summary)

    payload["baseline_slug"] = BASELINE_SLUG
    payload["rows"] = [asdict(r) for r in rows]
    payload["summary_by_model"] = summary
    payload["hypotheses"] = hypotheses
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attach wer_vs_baseline / cer_vs_baseline from transcripts/"
    )
    parser.add_argument(
        "results_dir",
        type=Path,
        help="Benchmark run directory (e.g. benchmark/results/20260521_100914)",
    )
    args = parser.parse_args()

    run_dir = args.results_dir.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Not a directory: {run_dir}")

    payload = recompute(run_dir)
    json_path = run_dir / "results.json"
    csv_path = run_dir / "results.csv"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [_row_from_dict(r) for r in payload["rows"]]
    _write_csv(csv_path, rows)

    print(f"Updated {json_path}")
    print(f"Updated {csv_path}")
    print(f"\n--- Summary (avg WER vs {BASELINE_SLUG}) ---")
    for slug, data in payload["summary_by_model"].items():
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

    for h in payload.get("hypotheses", []):
        status = "PASS" if h.get("passed") else ("FAIL" if h.get("passed") is False else "N/A")
        print(f"  {h['id']}: {status}")
        if "delta" in h:
            print(f"       delta WER={h['delta']:+.2%}")


if __name__ == "__main__":
    main()
