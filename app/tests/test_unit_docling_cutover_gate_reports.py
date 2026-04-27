"""Unit tests for Docling hard-cutover gate/report scripts."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import scripts.generate_docling_cutover_audit_report as docling_cutover_audit_report
import scripts.generate_retrieval_contract_report as retrieval_contract_report


def _load_standalone_script(module_name: str):
    scripts_dir = Path.cwd() / "scripts"
    scripts_path = str(scripts_dir)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    return importlib.import_module(module_name)


def _workspace_case_dir(name: str) -> Path:
    base = Path(".pytest-inline") / name
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    return base


def test_docling_cutover_report_flags_formats_when_doc_or_ppt_are_still_supported(monkeypatch) -> None:
    tmp_path = _workspace_case_dir("cutover-flags")
    parser_target = tmp_path / "parser_target.py"
    parser_target.write_text("def parse():\n    return None\n", encoding="utf-8")
    truth_artifact = tmp_path / "truth_artifact.json"
    truth_artifact.write_text(json.dumps({"gate_status": "PASS", "slots": [{"slot_id": "s1"}]}), encoding="utf-8")

    monkeypatch.setattr(
        docling_cutover_audit_report,
        "get_document_parser_capabilities",
        lambda: {"doc": True, "ppt": True},
    )
    monkeypatch.setattr(docling_cutover_audit_report, "is_ingestion_file_type_supported", lambda _file_type: True)

    report = docling_cutover_audit_report._build_report(
        parser_targets=[parser_target],
        truth_artifact_path=truth_artifact,
    )

    assert report["gate_status"] == "FAIL"
    assert report["blocked_format_rejection_matrix_passed"] is False
    assert {item["file_type"] for item in report["blocked_format_violations"]} == {"doc", "ppt"}


def test_docling_cutover_report_detects_legacy_parser_tokens_in_target_file(monkeypatch) -> None:
    tmp_path = _workspace_case_dir("legacy-token-detect")
    parser_target = tmp_path / "parser_target.py"
    parser_target.write_text(
        "\n".join(
            [
                "def parser():",
                "    return _parse_doc_document('demo')",
                "if isinstance(document, list):",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )
    truth_artifact = tmp_path / "truth_artifact.json"
    truth_artifact.write_text(json.dumps({"gate_status": "PASS", "slots": [{"slot_id": "s1"}]}), encoding="utf-8")

    monkeypatch.setattr(
        docling_cutover_audit_report,
        "get_document_parser_capabilities",
        lambda: {"doc": False, "ppt": False},
    )
    monkeypatch.setattr(docling_cutover_audit_report, "is_ingestion_file_type_supported", lambda _file_type: False)

    report = docling_cutover_audit_report._build_report(
        parser_targets=[parser_target],
        truth_artifact_path=truth_artifact,
    )

    assert report["parser_truth_passed"] is False
    assert report["gate_status"] == "FAIL"
    assert any(item["token"] == "_parse_doc_document" for item in report["parser_truth_violations"])


def test_retrieval_contract_report_fails_when_evidence_block_required_fields_are_missing() -> None:
    tmp_path = _workspace_case_dir("retrieval-contract-missing")
    target = tmp_path / "retrieval_service.py"
    target.write_text(
        "\n".join(
            [
                "from app.schemas.retrieval import EvidenceBlockHit",
                "def build():",
                "    return EvidenceBlockHit(",
                "        evidence_block_id='e1',",
                "        knowledge_point_id='k1',",
                "        title='t',",
                "        content='c',",
                "        score=0.1,",
                "        group_type='section',",
                "        anchor_chunk_indices=[0],",
                "    )",
            ]
        ),
        encoding="utf-8",
    )

    report = retrieval_contract_report._build_report(target)

    assert report["gate_status"] == "FAIL"
    assert report["retrieval_metadata_contract_ok"] is False
    assert any(item["reason"] == "EVIDENCE_FIELD_MISSING" for item in report["metadata_contract_violations"])


def test_sample_manifest_lock_report_fails_when_manifest_contains_unlocked_sample() -> None:
    sample_manifest_lock_report = _load_standalone_script("generate_sample_manifest_lock_report")
    tmp_path = _workspace_case_dir("manifest-lock-mismatch")

    manifest_path = tmp_path / "sample_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "samples": [{"sample_id": "sample-a", "content_sha256": "hash-a", "category": "user_retrieval"}],
                "category_minimums": {"user_retrieval": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    lock_path = tmp_path / "sample_lock.json"
    lock_path.write_text(
        json.dumps(
            {
                "manifest_sha256": sample_manifest_lock_report.sha256_file(manifest_path),
                "samples": [],
                "category_minimums": {"user_retrieval": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = sample_manifest_lock_report._build_report(manifest_path, lock_path)

    assert report["gate_status"] == "FAIL"
    assert report["unlocked_new_sample_ids"] == ["sample-a"]
