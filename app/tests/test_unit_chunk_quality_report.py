"""Unit tests for chunk quality gate aggregation rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import scripts.generate_chunk_quality_report as chunk_quality_report


@dataclass
class _FakeDocument:
    document_metadata: dict[str, object]
    parser_name: str = "parser"


@dataclass
class _FakeBundle:
    document_metadata: dict[str, object]
    chunks: list[dict[str, object]]


def test_chunk_quality_report_uses_global_chunk_ratios_not_document_average(
    monkeypatch,
) -> None:
    tmp_dir = Path(".tmp") / f"chunk-quality-{uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    large_doc = tmp_dir / "large.md"
    small_doc = tmp_dir / "small.md"
    large_doc.write_text("# large", encoding="utf-8")
    small_doc.write_text("# small", encoding="utf-8")

    def _fake_parse_document_artifact(file_path: str, file_type: str) -> _FakeDocument:
        _ = file_type
        if Path(file_path).name == "large.md":
            return _FakeDocument(document_metadata={"short_chunk_ratio": 0.8, "duplicate_chunk_ratio": 0.0})
        return _FakeDocument(document_metadata={"short_chunk_ratio": 0.0, "duplicate_chunk_ratio": 0.0})

    def _fake_build_chunk_bundle(*, file_type: str, document: _FakeDocument) -> _FakeBundle:
        _ = file_type
        if float(document.document_metadata["short_chunk_ratio"]) == 0.8:
            chunks = [
                {
                    "metadata_json": {
                        "block_type": "paragraph",
                        "chunker_type": "hybrid_text",
                        "token_count": 20,
                        "provenance": [{"page_number": 1}],
                        "quality_status": "short" if index < 8 else "ok",
                    }
                }
                for index in range(10)
            ]
            return _FakeBundle(
                document_metadata={
                    "parser_name": "parser",
                    "ocr_used": False,
                    "extracted_char_count": 1000,
                    "avg_chunk_chars": 100,
                    "short_chunk_ratio": 0.8,
                    "duplicate_chunk_ratio": 0.0,
                    "table_block_count": 0,
                    "image_block_count": 0,
                    "quality_status": "warn",
                },
                chunks=chunks,
            )
        return _FakeBundle(
            document_metadata={
                "parser_name": "parser",
                "ocr_used": False,
                "extracted_char_count": 500,
                "avg_chunk_chars": 250,
                "short_chunk_ratio": 0.0,
                "duplicate_chunk_ratio": 0.0,
                "table_block_count": 0,
                "image_block_count": 0,
                "quality_status": "passed",
            },
            chunks=[
                {
                    "metadata_json": {
                        "block_type": "paragraph",
                        "chunker_type": "hybrid_text",
                        "token_count": 100,
                        "provenance": [{"page_number": 2}],
                        "quality_status": "ok",
                    }
                }
            ],
        )

    monkeypatch.setattr(chunk_quality_report, "parse_document_artifact", _fake_parse_document_artifact)
    monkeypatch.setattr(chunk_quality_report, "build_chunk_bundle", _fake_build_chunk_bundle)

    report = chunk_quality_report._build_report(tmp_dir, max_short_ratio=0.40, max_duplicate_ratio=0.20)

    assert report["short_chunk_ratio"] == 0.7273
    assert report["gate_status"] == "FAIL"
    assert any(item["reason"] == "SHORT_CHUNK_RATIO_EXCEEDED" for item in report["violations"])
