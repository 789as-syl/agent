"""Generate the external baseline audit for locked real-problem samples."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sample_gate_utils import now_iso, sha256_file, write_json

REQUIRED_RETRIEVAL_SLOTS = (
    "slot_user_retrieval_r1",
    "slot_user_retrieval_r2",
    "slot_user_retrieval_r3",
)
REQUIRED_QUESTION_SLOTS = (
    "slot_question_bank_q1",
    "slot_question_bank_q2",
    "slot_question_bank_q3",
)


def _assert_existing_file(path: Path, label: str) -> Path:
    if not path.exists() or not path.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {path}")
    return path


def _slot_payload(slot_id: str, source_kind: str, sample_path: Path, captured_by: str) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "bound_sample_id": slot_id,
        "source_kind": source_kind,
        "source_path_or_uri": str(sample_path),
        "content_sha256": sha256_file(sample_path),
        "stable_name": sample_path.name,
        "captured_at_utc": now_iso(),
        "captured_by": captured_by,
    }


def _build_report(
    *,
    failing_docx: Path,
    failing_pdf: Path,
    retrieval_samples: list[Path],
    question_bank_samples: list[Path],
    captured_by: str,
) -> dict[str, Any]:
    if len(retrieval_samples) < len(REQUIRED_RETRIEVAL_SLOTS):
        raise ValueError("At least 3 retrieval samples are required")
    if len(question_bank_samples) < len(REQUIRED_QUESTION_SLOTS):
        raise ValueError("At least 3 question-bank samples are required")

    slots = [
        _slot_payload("slot_failing_docx_primary", "failing_docx", failing_docx, captured_by),
        _slot_payload("slot_failing_pdf_primary", "failing_pdf", failing_pdf, captured_by),
    ]
    slots.extend(
        _slot_payload(slot_id, "user_retrieval", sample_path, captured_by)
        for slot_id, sample_path in zip(REQUIRED_RETRIEVAL_SLOTS, retrieval_samples[:3], strict=True)
    )
    slots.extend(
        _slot_payload(slot_id, "question_bank", sample_path, captured_by)
        for slot_id, sample_path in zip(REQUIRED_QUESTION_SLOTS, question_bank_samples[:3], strict=True)
    )

    return {
        "report_version": "1.0",
        "generated_at": now_iso(),
        "gate_name": "external_baseline_anchor",
        "gate_status": "PASS",
        "baseline_name": "kb_doc_preview_external_baseline",
        "required_slot_count": 8,
        "required_slots": [slot["slot_id"] for slot in slots],
        "slots": slots,
        "source_summary": {
            "failing_docx": str(failing_docx),
            "failing_pdf": str(failing_pdf),
            "retrieval_samples": [str(path) for path in retrieval_samples[:3]],
            "question_bank_samples": [str(path) for path in question_bank_samples[:3]],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failing-docx", type=Path, required=True)
    parser.add_argument("--failing-pdf", type=Path, required=True)
    parser.add_argument("--retrieval-sample", type=Path, action="append", default=[])
    parser.add_argument("--question-bank-sample", type=Path, action="append", default=[])
    parser.add_argument("--captured-by", default="codex")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = _build_report(
        failing_docx=_assert_existing_file(args.failing_docx, "failing-docx"),
        failing_pdf=_assert_existing_file(args.failing_pdf, "failing-pdf"),
        retrieval_samples=[_assert_existing_file(path, "retrieval-sample") for path in args.retrieval_sample],
        question_bank_samples=[
            _assert_existing_file(path, "question-bank-sample") for path in args.question_bank_sample
        ],
        captured_by=str(args.captured_by),
    )
    write_json(args.output, report)
    print(f"[external_baseline_anchor] PASS -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

