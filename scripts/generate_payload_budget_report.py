"""Generate payload budget gate report JSON."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.document_processing import build_chunk_bundle, parse_document_artifact

REPORT_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _percentile(values: list[int], quantile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return int(ordered[index])


def _collect_payload_samples(input_dir: Path) -> list[int]:
    if not input_dir.exists():
        return []
    samples: list[int] = []
    for path in input_dir.rglob("*"):
        if not path.is_file():
            continue
        file_type = path.suffix.lower().lstrip(".")
        try:
            document = parse_document_artifact(str(path), file_type)
            bundle = build_chunk_bundle(file_type=file_type, document=document)
        except Exception:
            continue
        for chunk in bundle.chunks:
            content = str(chunk.get("content") or "")
            metadata = dict(chunk.get("metadata_json") or {})
            payload = {
                "content": content,
                "heading_path": metadata.get("heading_path"),
                "provenance": metadata.get("provenance"),
                "block_type": metadata.get("block_type"),
                "group_id": metadata.get("anchor_group_id"),
            }
            samples.append(len(json.dumps(payload, ensure_ascii=False).encode("utf-8")))
    return samples


def _build_report(input_dir: Path, p95_limit: int, p99_limit: int) -> dict[str, Any]:
    payload_samples = _collect_payload_samples(input_dir)
    payload_p95 = _percentile(payload_samples, 0.95)
    payload_p99 = _percentile(payload_samples, 0.99)

    limits = {
        "evidence_block_max_chars": 2400,
        "tool_payload_max_bytes": 32768,
        "execution_trace_metadata_max_bytes": 8192,
        "run_event_json_max_bytes": 65536,
        "message_metadata_max_bytes": 16384,
        "payload_p95_max_bytes": int(p95_limit),
        "payload_p99_max_bytes": int(p99_limit),
    }

    violations: list[dict[str, Any]] = []
    if not payload_samples:
        violations.append({"metric": "payload_samples", "reason": "NO_INPUT_SAMPLES"})
    if payload_p95 > p95_limit:
        violations.append(
            {
                "metric": "payload_p95_bytes",
                "observed": payload_p95,
                "limit": p95_limit,
            }
        )
    if payload_p99 > p99_limit:
        violations.append(
            {
                "metric": "payload_p99_bytes",
                "observed": payload_p99,
                "limit": p99_limit,
            }
        )

    gate_status = "PASS" if not violations else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "payload_budget_gate",
        "gate_status": gate_status,
        "payload_p95_bytes": payload_p95,
        "payload_p99_bytes": payload_p99,
        "limits": limits,
        "violations": violations,
        "sample_count": len(payload_samples),
        "input_dir": str(input_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data_example"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--p95-max-bytes", type=int, default=24576)
    parser.add_argument("--p99-max-bytes", type=int, default=49152)
    args = parser.parse_args()

    report = _build_report(args.input_dir, args.p95_max_bytes, args.p99_max_bytes)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[payload_budget_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
