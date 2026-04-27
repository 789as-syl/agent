"""Generate durable artifact reuse report."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

REPORT_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_report(targets: list[Path]) -> dict[str, object]:
    joined = "\n".join(path.read_text(encoding="utf-8") for path in targets if path.exists())
    has_only_local_cache = '.omx/cache/docling' in joined and 'artifact_object_path' not in joined
    violations = []
    if has_only_local_cache:
        violations.append(
            {
                "reason": "DURABLE_ARTIFACT_NOT_IMPLEMENTED",
                "detail": "Only local cache_path wiring found; no durable artifact object path/signature wiring detected",
            }
        )
    gate_status = "PASS" if not violations else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "artifact_reuse_gate",
        "gate_status": gate_status,
        "artifact_store": "local_cache_only" if has_only_local_cache else "durable_or_unknown",
        "reuse_hit_count": 0,
        "forced_reparse_count": 0,
        "signature_mismatches": [],
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    targets = args.target or [Path("app/services/document_processing.py"), Path("app/tasks/ingestion_tasks.py")]
    report = _build_report(targets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[artifact_reuse_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
