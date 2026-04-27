"""Generate retrieval contract gate report JSON."""

from __future__ import annotations

import argparse
import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.retrieval.retrieval_service import RetrievalService
from app.tools.result_protocol import TOOL_PROTOCOL_VERSION

REPORT_VERSION = "1.0"
FORBIDDEN_RUNTIME_METHODS = {"vector_search", "get_knowledge_point_mapping"}
REQUIRED_EVIDENCE_FIELDS = {
    "evidence_block_id",
    "knowledge_point_id",
    "title",
    "content",
    "score",
    "group_type",
    "anchor_chunk_indices",
    "provenance",
}
REQUIRED_DOCILING_METADATA_FIELDS = {
    "docling_group_id",
    "docling_group_type",
    "provenance",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _find_forbidden_calls(target: Path) -> list[dict[str, Any]]:
    source = target.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in FORBIDDEN_RUNTIME_METHODS:
            continue

        receiver = ast.unparse(func.value)
        if "question_repo" not in receiver:
            continue

        violations.append(
            {
                "line": getattr(node, "lineno", None),
                "call": f"{receiver}.{func.attr}",
                "reason": "RUNTIME_QUESTION_CALL_FORBIDDEN",
            }
        )

    return violations


def _find_evidence_field_violations(target: Path) -> list[dict[str, Any]]:
    source = target.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "EvidenceBlockHit":
            continue

        provided = {keyword.arg for keyword in node.keywords if keyword.arg}
        missing = sorted(REQUIRED_EVIDENCE_FIELDS - provided)
        if missing:
            violations.append(
                {
                    "line": getattr(node, "lineno", None),
                    "reason": "EVIDENCE_FIELD_MISSING",
                    "missing_fields": missing,
                }
            )

    return violations


def _find_docling_metadata_contract_violations(target: Path) -> list[dict[str, Any]]:
    source = target.read_text(encoding="utf-8")
    tree = ast.parse(source)
    observed_string_literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    missing = sorted(field for field in REQUIRED_DOCILING_METADATA_FIELDS if field not in observed_string_literals)
    if not missing:
        return []
    return [{"reason": "DOCILING_METADATA_FIELD_MISSING", "missing_fields": missing}]


def _build_report(target: Path) -> dict[str, Any]:
    forbidden_call_violations = _find_forbidden_calls(target)
    violations = list(forbidden_call_violations)
    metadata_contract_violations = _find_evidence_field_violations(target)
    violations.extend(metadata_contract_violations)
    docling_metadata_violations = _find_docling_metadata_contract_violations(target)
    violations.extend(docling_metadata_violations)
    runtime_smoke_error: str | None = None
    try:
        service = RetrievalService.__new__(RetrievalService)
        RetrievalService._build_evidence_content(
            service,
            [
                type(
                    "CompatChunk",
                    (),
                    {
                        "chunk_index": 0,
                        "content": "evidence",
                        "metadata_json": {"provenance": [{"page_number": 1}]},
                    },
                )(),
                type(
                    "CompatChunkDict",
                    (),
                    {
                        "chunk_index": 1,
                        "content": "evidence-2",
                        "metadata_json": {"provenance": {"page_number": 2}},
                    },
                )(),
            ],
            {"anchor_group_type": "section"},
            table_neighbor_rows=1,
        )
    except Exception as exc:  # pragma: no cover - report generation safety
        runtime_smoke_error = str(exc)
        violations.append({"reason": "RUNTIME_SMOKE_FAILED", "error": str(exc)})
    questions_runtime_calls_detected = len(forbidden_call_violations) > 0
    retrieval_metadata_contract_ok = len(metadata_contract_violations) == 0
    docling_metadata_contract_ok = len(docling_metadata_violations) == 0
    gate_status = "PASS" if not violations else "FAIL"
    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "retrieval_contract_gate",
        "gate_status": gate_status,
        "evidence_schema_version": TOOL_PROTOCOL_VERSION,
        "questions_runtime_calls_detected": questions_runtime_calls_detected,
        "retrieval_metadata_contract_ok": retrieval_metadata_contract_ok,
        "docling_metadata_contract_ok": docling_metadata_contract_ok,
        "runtime_smoke_error": runtime_smoke_error,
        "metadata_contract_violations": metadata_contract_violations,
        "docling_metadata_contract_violations": docling_metadata_violations,
        "violations": violations,
        "target": str(target),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("app/services/retrieval/retrieval_service.py"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = _build_report(args.target)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[retrieval_contract_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
