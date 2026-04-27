"""Aggregate per-sample WS4 regression results into a gate report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sample_gate_utils import load_structured_file, now_iso, write_json


def _sample_ids(payload: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for sample in payload.get("samples") or []:
        if not isinstance(sample, dict):
            continue
        sample_id = str(sample.get("sample_id") or "").strip()
        if sample_id:
            result.append(sample_id)
    return result


def _load_result_entries(paths: list[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            entries.append(payload)
        elif isinstance(payload, list):
            entries.extend(item for item in payload if isinstance(item, dict))
    return entries


def _build_report(sample_manifest: Path, sample_lock: Path | None, result_paths: list[Path]) -> dict[str, Any]:
    manifest = load_structured_file(sample_manifest)
    required_ids = set(_sample_ids(manifest))
    if sample_lock is not None and sample_lock.exists():
        required_ids &= set(_sample_ids(load_structured_file(sample_lock))) or required_ids

    if not result_paths:
        return {
            "report_version": "1.0",
            "generated_at": now_iso(),
            "gate_name": "ws4_real_sample_regression_gate",
            "gate_status": "FAIL",
            "coverage_ratio": 0.0,
            "covered_sample_ids": [],
            "failed_sample_ids": [],
            "violations": [{"reason": "NO_RESULT_FILES"}],
        }

    entries = _load_result_entries(result_paths)
    result_map: dict[str, dict[str, Any]] = {}
    for entry in entries:
        sample_id = str(entry.get("sample_id") or "").strip()
        if sample_id:
            result_map[sample_id] = entry

    covered_sample_ids = sorted(sample_id for sample_id in required_ids if sample_id in result_map)
    failed_sample_ids = sorted(
        sample_id
        for sample_id in covered_sample_ids
        if not bool(result_map[sample_id].get("passed", result_map[sample_id].get("status") == "PASS"))
    )
    missing_sample_ids = sorted(sample_id for sample_id in required_ids if sample_id not in result_map)
    coverage_ratio = round(len(covered_sample_ids) / max(1, len(required_ids)), 4)
    violations: list[dict[str, Any]] = []
    if missing_sample_ids:
        violations.append({"reason": "MISSING_SAMPLE_RESULTS", "sample_ids": missing_sample_ids})
    if failed_sample_ids:
        violations.append({"reason": "FAILED_SAMPLE_RESULTS", "sample_ids": failed_sample_ids})
    status = "PASS" if not violations else "FAIL"
    return {
        "report_version": "1.0",
        "generated_at": now_iso(),
        "gate_name": "ws4_real_sample_regression_gate",
        "gate_status": status,
        "coverage_ratio": coverage_ratio,
        "covered_sample_ids": covered_sample_ids,
        "failed_sample_ids": failed_sample_ids,
        "missing_sample_ids": missing_sample_ids,
        "result_files": [str(path) for path in result_paths],
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--sample-lock", type=Path)
    parser.add_argument("--result", type=Path, action="append", default=[])
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result_paths = list(args.result)
    if args.results_dir and args.results_dir.exists():
        result_paths.extend(sorted(path for path in args.results_dir.glob("*.json") if path.is_file()))

    report = _build_report(args.sample_manifest, args.sample_lock, result_paths)
    write_json(args.output, report)
    print(f"[ws4_real_sample_regression_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

