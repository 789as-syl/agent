"""Aggregate gate reports and generate summary gate JSON."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPORT_VERSION = "1.0"
EXPECTED_REPORTS = [
    "blocked-format-contract-report.json",
    "conversion-readiness-report.json",
    "parser-truth-report.json",
    "artifact-reuse-report.json",
    "chunk-quality-report.json",
    "retrieval-contract-report.json",
    "sample-manifest-lock-report.json",
    "ws4-real-sample-regression-report.json",
    "legacy-parser-backfill-report.json",
    "truth-artifact-audit-report.json",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _build_summary(report_paths: list[Path]) -> dict[str, Any]:
    found_reports = [path.name for path in report_paths if path.exists()]
    missing_reports = [name for name in EXPECTED_REPORTS if name not in found_reports]

    per_gate_status: dict[str, str] = {}
    failed_gates: list[str] = []
    parse_errors: list[dict[str, str]] = []

    for path in report_paths:
        if not path.exists():
            continue

        payload = _load_json(path)
        if payload is None:
            parse_errors.append({"report": path.name, "reason": "INVALID_JSON"})
            failed_gates.append(f"{path.name}:INVALID_JSON")
            continue

        gate_name = str(payload.get("gate_name") or path.stem)
        gate_status = str(payload.get("gate_status") or payload.get("summary_gate_status") or "UNKNOWN")
        per_gate_status[gate_name] = gate_status
        if gate_status != "PASS":
            failed_gates.append(gate_name)

    for missing in missing_reports:
        failed_gates.append(f"{missing}:MISSING")

    summary_gate_status = "PASS" if not failed_gates else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "gate_summary_gate",
        "gate_status": summary_gate_status,
        "summary_gate_status": summary_gate_status,
        "expected_reports": EXPECTED_REPORTS,
        "found_reports": found_reports,
        "missing_reports": missing_reports,
        "failed_gates": failed_gates,
        "per_gate_status": per_gate_status,
        "parse_errors": parse_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    summary = _build_summary(args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gate_summary_gate] {summary['summary_gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
