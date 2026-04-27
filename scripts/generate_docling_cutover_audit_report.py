"""Generate Docling hard-cutover audit report JSON."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.document_processing import get_document_parser_capabilities, is_ingestion_file_type_supported

REPORT_VERSION = "1.0"
BLOCKED_FORMATS = ("doc", "ppt")
LEGACY_PARSER_TOKENS = (
    "_parse_doc_document",
    "_parse_ppt_document",
    "legacy_cfb_doc",
    "legacy_cfb_ppt",
    "legacy_sections",
    "parser_name=\"compat\"",
    "if isinstance(document, list)",
)
TRUTH_ARTIFACT_REQUIRED_KEYS = ("gate_status", "slots")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _scan_legacy_parser_leakage(target: Path) -> list[dict[str, Any]]:
    if not target.exists():
        return [{"reason": "PARSER_TARGET_MISSING", "target": str(target)}]

    text = target.read_text(encoding="utf-8")
    violations: list[dict[str, Any]] = []
    for token in LEGACY_PARSER_TOKENS:
        if token not in text:
            continue
        line = next(
            (
                line_number
                for line_number, line_text in enumerate(text.splitlines(), start=1)
                if token in line_text
            ),
            None,
        )
        violations.append(
            {
                "reason": "LEGACY_PARSER_LEAKAGE",
                "target": str(target),
                "token": token,
                "line": line,
            }
        )
    return violations


def _truth_artifact_violations(truth_artifact_path: Path) -> list[dict[str, Any]]:
    if not truth_artifact_path.exists():
        return [
            {
                "reason": "TRUTH_ARTIFACT_MISSING",
                "path": str(truth_artifact_path),
            }
        ]

    try:
        payload = json.loads(truth_artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [{"reason": "TRUTH_ARTIFACT_INVALID_JSON", "path": str(truth_artifact_path), "error": str(exc)}]

    if not isinstance(payload, dict):
        return [{"reason": "TRUTH_ARTIFACT_INVALID_SHAPE", "path": str(truth_artifact_path)}]

    if {"binding_status", "manifest_sha256", "samples"}.issubset(payload):
        binding_status = str(payload.get("binding_status") or "")
        manifest_sha256 = str(payload.get("manifest_sha256") or "")
        samples = payload.get("samples")
        if binding_status == "BOUND" and manifest_sha256 and isinstance(samples, list) and len(samples) > 0:
            return []
        return [
            {
                "reason": "TRUTH_ARTIFACT_UNBOUND",
                "path": str(truth_artifact_path),
                "binding_status": binding_status,
                "sample_count": len(samples) if isinstance(samples, list) else 0,
            }
        ]

    missing_keys = [key for key in TRUTH_ARTIFACT_REQUIRED_KEYS if key not in payload]
    if missing_keys:
        return [
            {
                "reason": "TRUTH_ARTIFACT_KEYS_MISSING",
                "path": str(truth_artifact_path),
                "missing_keys": missing_keys,
            }
        ]

    gate_status = str(payload.get("gate_status") or "")
    slots = payload.get("slots")
    if gate_status.upper() in {"", "UNBOUND"} or not isinstance(slots, list) or len(slots) == 0:
        return [
            {
                "reason": "TRUTH_ARTIFACT_UNBOUND",
                "path": str(truth_artifact_path),
                "gate_status": gate_status,
                "slot_count": len(slots) if isinstance(slots, list) else 0,
            }
        ]

    return []


def _build_report(*, parser_targets: list[Path], truth_artifact_path: Path) -> dict[str, Any]:
    capabilities = get_document_parser_capabilities()
    blocked_format_violations: list[dict[str, Any]] = []
    for file_type in BLOCKED_FORMATS:
        capability_enabled = bool(capabilities.get(file_type, False))
        ingestion_enabled = bool(is_ingestion_file_type_supported(file_type))
        if capability_enabled or ingestion_enabled:
            blocked_format_violations.append(
                {
                    "reason": "BLOCKED_FORMAT_STILL_ACCEPTED",
                    "file_type": file_type,
                    "capability_enabled": capability_enabled,
                    "ingestion_enabled": ingestion_enabled,
                }
            )

    parser_truth_violations: list[dict[str, Any]] = []
    for path in parser_targets:
        parser_truth_violations.extend(_scan_legacy_parser_leakage(path))

    truth_artifact_violations = _truth_artifact_violations(truth_artifact_path)
    violations = blocked_format_violations + parser_truth_violations + truth_artifact_violations
    gate_status = "PASS" if not violations else "FAIL"

    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "docling_cutover_audit_gate",
        "gate_status": gate_status,
        "blocked_formats": list(BLOCKED_FORMATS),
        "blocked_format_rejection_matrix_passed": len(blocked_format_violations) == 0,
        "blocked_format_violations": blocked_format_violations,
        "parser_truth_passed": len(parser_truth_violations) == 0,
        "parser_truth_targets": [str(path) for path in parser_targets],
        "parser_truth_violations": parser_truth_violations,
        "truth_artifact_bound": len(truth_artifact_violations) == 0,
        "truth_artifact_path": str(truth_artifact_path),
        "truth_artifact_violations": truth_artifact_violations,
        "legacy_parser_backfill_truth_audit_ready": len(truth_artifact_violations) == 0,
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parser-target",
        action="append",
        type=Path,
        default=[],
        help="Python file to scan for legacy parser leakage",
    )
    parser.add_argument(
        "--truth-artifact",
        type=Path,
        default=Path(".omx/specs/docling-hard-cutover-samples.lock.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    parser_targets = args.parser_target or [
        Path("app/services/document_processing.py"),
        Path("app/tasks/ingestion_tasks.py"),
    ]
    report = _build_report(
        parser_targets=parser_targets,
        truth_artifact_path=args.truth_artifact,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[docling_cutover_audit_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
