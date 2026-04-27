"""Unit tests for document parsing and chunk metadata helpers."""

from __future__ import annotations

from pathlib import Path

from app.services import document_processing
from app.services.document_processing import DoclingBlock, DoclingDocument, ParsedSection


def test_parse_document_artifact_rejects_blocked_formats() -> None:
    blocked_path = Path("data_example/《创业沙盘》课程计划(教学大纲)-刘显铭.doc")

    try:
        document_processing.parse_document_artifact(str(blocked_path), "doc")
    except ValueError as exc:
        assert "Unsupported file type" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("blocked legacy format should not parse")


def test_get_missing_document_parser_types_respects_allowed_types(monkeypatch):
    monkeypatch.setattr(
        document_processing,
        "get_document_parser_capabilities",
        lambda: {"pdf": False, "md": True, "txt": True, "docx": True},
    )

    assert document_processing.get_missing_document_parser_types(["pdf", "md"]) == ["pdf"]


def test_build_chunk_payloads_enriches_chunk_metadata():
    payloads = document_processing.build_chunk_payloads(
        file_type="md",
        sections=[
            ParsedSection(text="第一块\n第二行", metadata={"page_number": 2}),
            ParsedSection(text="第二块", metadata={"header_path": "章节 1"}),
        ],
        chunk_size_text=600,
        chunk_overlap_text=60,
        chunk_size_markdown=800,
        chunk_overlap_markdown=80,
    )

    assert len(payloads) == 2
    assert payloads[0]["chunk_index"] == 0
    assert payloads[0]["content"] == "第一块\n第二行"
    assert payloads[0]["metadata_json"]["file_type"] == "md"
    assert payloads[0]["metadata_json"]["page_number"] == 2
    assert payloads[0]["metadata_json"]["char_count"] == len("第一块\n第二行")
    assert payloads[0]["metadata_json"]["line_count"] == 2
    assert payloads[0]["metadata_json"]["approx_token_count"] > 0
    assert payloads[1]["metadata_json"]["header_path"] == "章节 1"


def test_generated_preview_supports_pptx_and_renders_structured_blocks() -> None:
    document = DoclingDocument(
        file_type="pptx",
        source_path="data_example/_smoke_sample.pptx",
        title="回归 PPTX",
        parser_name="upstream_docling:test",
        ocr_used=False,
        blocks=[
            DoclingBlock(
                block_id="heading-1",
                block_type="heading",
                text="回归 PPTX",
                heading_path=["回归 PPTX"],
                provenance={"slide_number": 1, "page_number": 1},
            ),
            DoclingBlock(
                block_id="paragraph-1",
                block_type="paragraph",
                text="这是一个有效的 PPTX smoke 样本。",
                heading_path=["回归 PPTX"],
                provenance={"slide_number": 1, "page_number": 1},
            ),
            DoclingBlock(
                block_id="list-1",
                block_type="list",
                text="- 第一条要点",
                heading_path=["回归 PPTX"],
                provenance={"slide_number": 1, "page_number": 1},
            ),
            DoclingBlock(
                block_id="table-1",
                block_type="table",
                text="表头:列1 | 列2 | 表行:A | B",
                heading_path=["回归 PPTX"],
                provenance={"slide_number": 2, "page_number": 2},
                caption="示例表格",
                metadata={"headers": ["列1", "列2"], "rows": [["A", "B"]]},
            ),
        ],
        extracted_char_count=42,
        table_block_count=1,
        image_block_count=0,
    )

    preview_html = document_processing.build_preview_html_artifact(document=document, max_chars=5000)

    assert document_processing.is_generated_preview_supported("pptx") is True
    assert "结构化幻灯片预览" in preview_html
    assert "第 1 张幻灯片" in preview_html
    assert "第 2 张幻灯片" in preview_html
    assert "这是一个有效的 PPTX smoke 样本。" in preview_html
    assert "<li>" in preview_html
    assert "示例表格" in preview_html
    assert "<table class='preview-table'>" in preview_html
