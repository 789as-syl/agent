"""Validate required slots in the external baseline audit report."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sample_gate_utils import load_structured_file, now_iso, write_json


def _build_report(baseline: dict[str, Any], required_slots: list[str]) -> dict[str, Any]:
    slots = baseline.get("slots") or []
    slot_map: dict[str, list[dict[str, Any]]] = {}
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        slot_id = str(slot.get("slot_id") or "").strip()
        if not slot_id:
            continue
        slot_map.setdefault(slot_id, []).append(slot)

    missing_slots: list[str] = []
    duplicate_slots: list[str] = []
    invalid_slots: list[str] = []
    for slot_id in required_slots:
        matches = slot_map.get(slot_id, [])
        if not matches:
            missing_slots.append(slot_id)
            continue
        if len(matches) > 1:
            duplicate_slots.append(slot_id)
        slot = matches[0]
        if not all(
            str(slot.get(field) or "").strip()
            for field in ("bound_sample_id", "source_kind", "source_path_or_uri", "content_sha256")
        ):
            invalid_slots.append(slot_id)

    status = "PASS" if not (missing_slots or duplicate_slots or invalid_slots) else "FAIL"
    return {
        "report_version": "1.0",
        "generated_at": now_iso(),
        "gate_name": "external_baseline_slot_validation",
        "gate_status": status,
        "slot_status": status,
        "required_slots": required_slots,
        "missing_slots": missing_slots,
        "duplicate_slots": duplicate_slots,
        "invalid_slots": invalid_slots,
        "baseline_required_slot_count": int(baseline.get("required_slot_count") or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--required-slots", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    baseline = load_structured_file(args.baseline)
    report = _build_report(baseline, [str(item) for item in args.required_slots])
    write_json(args.output, report)
    print(f"[external_baseline_slot_validation] {report['slot_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

