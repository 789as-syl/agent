"""Validate external anchor alignment with sample manifest and lock."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sample_gate_utils import load_structured_file, now_iso, write_json


def _sample_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for sample in payload.get("samples") or []:
        if not isinstance(sample, dict):
            continue
        sample_id = str(sample.get("sample_id") or "").strip()
        if sample_id:
            result[sample_id] = sample
    return result


def _slot_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for slot in payload.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        slot_id = str(slot.get("slot_id") or "").strip()
        if slot_id:
            result[slot_id] = slot
    return result


def _build_report(
    external_baseline_path: Path,
    sample_manifest_path: Path,
    sample_lock_path: Path,
    required_slots: list[str],
) -> dict[str, Any]:
    baseline = load_structured_file(external_baseline_path)
    manifest = load_structured_file(sample_manifest_path)
    lock = load_structured_file(sample_lock_path)

    slots = _slot_map(baseline)
    manifest_samples = _sample_map(manifest)
    lock_samples = _sample_map(lock)

    missing_required_slots: list[str] = []
    slot_hash_mismatches: list[str] = []
    slot_rebind_violations: list[str] = []
    matched_slots = 0

    for slot_id in required_slots:
        slot = slots.get(slot_id)
        if not slot:
            missing_required_slots.append(slot_id)
            continue
        bound_sample_id = str(slot.get("bound_sample_id") or "").strip()
        bound_hash = str(slot.get("content_sha256") or "").strip()
        if not bound_sample_id or not bound_hash:
            missing_required_slots.append(slot_id)
            continue

        manifest_sample = manifest_samples.get(bound_sample_id)
        lock_sample = lock_samples.get(bound_sample_id)
        if manifest_sample is None or lock_sample is None:
            slot_rebind_violations.append(slot_id)
            continue

        manifest_hash = str(manifest_sample.get("content_sha256") or "").strip()
        lock_hash = str(lock_sample.get("content_sha256") or "").strip()
        if manifest_hash != bound_hash or lock_hash != bound_hash:
            slot_hash_mismatches.append(slot_id)
            continue

        matched_slots += 1

    required_slot_coverage = round(matched_slots / max(1, len(required_slots)), 4)
    self_mutation_detected = bool(slot_hash_mismatches or slot_rebind_violations or missing_required_slots)
    status = "PASS" if not self_mutation_detected else "FAIL"
    return {
        "report_version": "1.0",
        "generated_at": now_iso(),
        "gate_name": "anchor_alignment_gate",
        "gate_status": status,
        "required_slots": required_slots,
        "required_slot_coverage": required_slot_coverage,
        "missing_required_slots": missing_required_slots,
        "slot_hash_mismatches": slot_hash_mismatches,
        "slot_rebind_violations": slot_rebind_violations,
        "self_mutation_detected": self_mutation_detected,
        "external_baseline_path": str(external_baseline_path),
        "sample_manifest_path": str(sample_manifest_path),
        "sample_lock_path": str(sample_lock_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-baseline", type=Path, required=True)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--sample-lock", type=Path, required=True)
    parser.add_argument("--required-slots", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = _build_report(
        args.external_baseline,
        args.sample_manifest,
        args.sample_lock,
        [str(item) for item in args.required_slots],
    )
    write_json(args.output, report)
    print(f"[anchor_alignment_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

