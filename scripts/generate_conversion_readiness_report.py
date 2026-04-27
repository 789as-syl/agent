"""Generate conversion readiness gate report JSON."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_ingestion_supported_file_types
from app.services.document_processing import (
    get_document_runtime_readiness,
    is_ingestion_file_type_supported,
    parse_document_sections,
)

REPORT_VERSION = "1.0"
REQUIRED_SAMPLE_MINIMUMS: dict[str, int] = {
    "docx": 2,
    "pptx": 1,
    "pdf": 1,
    "md": 1,
    "html": 1,
    "txt": 1,
}
BLOCKED_FORMATS: tuple[str, ...] = ("doc", "ppt")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_report(samples_dir: Path) -> dict[str, Any]:
    sample_files = [path for path in samples_dir.rglob("*") if path.is_file()]
    sample_counts = Counter(path.suffix.lower().lstrip(".") for path in sample_files if path.suffix)

    runtime_readiness = get_document_runtime_readiness(list(get_ingestion_supported_file_types()))
    docling_runtime_ready = bool(runtime_readiness.get("docling_runtime_ready"))
    docling_pdf_runtime_ready = bool(runtime_readiness.get("docling_pdf_runtime_ready"))
    docling_parser_ready = bool(runtime_readiness["docling_parser_ready"])

    failed_cases: list[dict[str, Any]] = []

    for file_type, expected_min in REQUIRED_SAMPLE_MINIMUMS.items():
        actual = int(sample_counts.get(file_type, 0))
        if actual < expected_min:
            failed_cases.append(
                {
                    "file_type": file_type,
                    "reason": "SAMPLE_MISSING",
                    "expected_min": expected_min,
                    "actual": actual,
                }
            )

    parser_checked_types = sorted({path.suffix.lower().lstrip(".") for path in sample_files if path.suffix})
    for file_type in parser_checked_types:
        if file_type in BLOCKED_FORMATS:
            continue
        if not is_ingestion_file_type_supported(file_type):
            failed_cases.append(
                {
                    "file_type": file_type,
                    "reason": "PARSER_MISSING",
                }
            )
            continue

        sample_path = next(
            (path for path in sample_files if path.suffix.lower().lstrip(".") == file_type),
            None,
        )
        if sample_path is None:
            continue
        try:
            parse_document_sections(str(sample_path), file_type)
        except Exception as exc:
            failed_cases.append(
                {
                    "file_type": file_type,
                    "reason": "SAMPLE_PARSE_FAILED",
                    "sample": str(sample_path),
                    "error": str(exc),
                }
            )

    sample_matrix_passed = len(failed_cases) == 0
    gate_status = (
        "PASS"
        if docling_runtime_ready and docling_pdf_runtime_ready and docling_parser_ready and sample_matrix_passed
        else "FAIL"
    )

    return {
        "report_version": REPORT_VERSION,
        "generated_at": _now_iso(),
        "gate_name": "conversion_readiness_gate",
        "gate_status": gate_status,
        "docling_ready": docling_runtime_ready,
        "docling_pdf_ready": docling_pdf_runtime_ready,
        "docling_version": None,
        "docling_parser_ready": docling_parser_ready,
        "supported_types": sorted(REQUIRED_SAMPLE_MINIMUMS),
        "blocked_types": list(BLOCKED_FORMATS),
        "sample_matrix_passed": sample_matrix_passed,
        "sample_matrix_failed_cases": failed_cases,
        "sample_matrix_counts": dict(sample_counts),
        "samples_dir": str(samples_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-dir", type=Path, default=Path("data_example"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = _build_report(args.samples_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[conversion_readiness_gate] {report['gate_status']} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
