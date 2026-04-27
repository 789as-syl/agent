"""Validate that a sample manifest matches its lock file."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sample_gate_utils import load_structured_file, normalized_category_counts, now_iso, sha256_file, write_json


def _sample_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for sample in payload.get("samples") or []:
        if not isinstance(sample, dict):
            continue
        sample_id = str(sample.get("sample_id") or "").strip()
        if sample_id:
            result[sample_id] = sample
    return result


def _build_report(manifest_path: Path, lock_path: Path) -> dict[str, Any]:
    manifest = load_structured_file(manifest_path)
    lock = load_structured_file(lock_path)
    manifest_sha256 = sha256_file(manifest_path)
    manifest_samples = _sample_map(manifest)
    lock_samples = _sample_map(lock)

    missing_sample_ids = sorted(sample_id for sample_id in lock_samples if sample_id not in manifest_samples)
    unlocked_new_sample_ids = sorted(sample_id for sample_id in manifest_samples if sample_id not in lock_samples)
    replaced_sample_ids = sorted(
        sample_id
        for sample_id, manifest_sample in manifest_samples.items()
        if sample_id in lock_samples
        and str(manifest_sample.get("content_sha256") or "") != str(lock_samples[sample_id].get("content_sha256") or "")
    )

    category_minimums = dict(lock.get("category_minimums") or manifest.get("category_minimums") or {})
    manifest_counts = normalized_category_counts(list(manifest_samples.values()))
    category_cardinality_below_min = sorted(
        category
        for category, minimum in category_minimums.items()
        if int(manifest_counts.get(category, 0)) < int(minimum or 0)
    )

    manifest_sha256_match = str(lock.get("manifest_sha256") or "") == manifest_sha256
    status = "PASS"
    if (
        not manifest_sha256_match
        or missing_sample_ids
        or unlocked_new_sample_ids
        or replaced_sample_ids
        or category_cardinality_below_min
    ):
        status = "FAIL"

    return {
        "report_version": "1.0",
        "generated_at": now_iso(),
        "gate_name": "sample_manifest_lock_gate",
        "gate_status": status,
        "pinning_status": status,
        "manifest_path": str(manifest_path),
        "lock_path": str(lock_path),
        "manifest_sha256": manifest_sha256,
        "manifest_sha256_match": manifest_sha256_match,
        "missing_sample_ids": missing_sample_ids,
        "replaced_sample_ids": replaced_sample_ids,
        "unlocked_new_sample_ids": unlocked_new_sample_ids,
        "category_cardinality_below_min": category_cardinality_below_min,
        "category_minimums": category_minimums,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--sample-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = _build_report(args.sample_manifest, args.sample_lock)
    write_json(args.output, report)
    print(f"[sample_manifest_lock_gate] {report['pinning_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

