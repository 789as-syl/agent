"""Generate truth-artifact audit report."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

REPORT_VERSION = "1.0"
BANNED_SNIPPETS = (
    ".doc/.ppt",
    "Docling-style",
    "legacy CFB",
    "当前环境直跑",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _scan(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "INVALIDATED REPORT NOTICE" in text or "SUPERSEDED ARTIFACT NOTICE" in text:
        return []
    violations: list[dict[str, object]] = []
    for snippet in BANNED_SNIPPETS:
        if snippet in text:
            violations.append({"artifact": str(path), "snippet": snippet})
    return violations


def _build_report(artifacts: list[Path]) -> dict[str, object]:
    contradictory_artifacts: list[dict[str, object]] = []
    active_truth_artifacts = [str(path) for path in artifacts if path.exists()]
    for artifact in artifacts:
        contradictory_artifacts.extend(_scan(artifact))
    gate_status = "PASS" if not contradictory_artifacts else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "truth_artifact_audit_gate",
        "gate_status": gate_status,
        "active_truth_artifacts": active_truth_artifacts,
        "contradictory_artifacts": contradictory_artifacts,
        "violations": contradictory_artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.artifact or [
        Path(".omx/plans/prd-kb-docling-ingestion-retrieval-overhaul.md"),
        Path(".omx/plans/test-spec-kb-docling-ingestion-retrieval-overhaul.md"),
        Path(".omx/reports/final-delivery-kb-docling-ingestion-retrieval-overhaul.md"),
    ]
    report = _build_report(artifacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[truth_artifact_audit_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
