"""Document parsing, normalization, caching, and chunking helpers."""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from statistics import mean
from typing import Any, cast

from app.core.config import (
    get_ingestion_supported_file_types,
    is_docling_pdf_runtime_available,
    is_docling_runtime_available,
)
from app.core.docling_runtime import ensure_docling_runtime_on_path
from app.core.log_config import get_logger

logger = get_logger(__name__)

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INLINE_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
_PAGE_NUMBER_RE = re.compile(r"^(?:第\s*\d+\s*页|page\s*\d+|\d+\s*/\s*\d+|\d+)$", re.I)
_FURNITURE_PREFIXES = ("目录", "版权所有", "Confidential", "版权声明")
_CACHE_DIR = Path(".omx/cache/docling")
_MAX_SECTION_TOKENS = 420
_MAX_TABLE_TOKENS = 260
_SHORT_CHUNK_CHAR_THRESHOLD = 120
_SHORT_CHUNK_TOKEN_THRESHOLD = 80
_PREVIEW_GENERATED_TYPES = {"docx", "md", "html", "txt", "pptx"}
PARSER_VERSION = "upstream_docling_v1"
CHUNKER_VERSION = "hybrid_chunk_bundle_v2"
CLEANING_PROFILE_ID = "default_cleaning_profile_v2"


@dataclass(slots=True)
class ParsedSection:
    text: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class DoclingBlock:
    block_id: str
    block_type: str
    text: str
    heading_path: list[str] = field(default_factory=list)
    anchor_group_type: str = "section"
    anchor_group_id: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)
    caption: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DoclingDocument:
    file_type: str
    source_path: str
    title: str
    parser_name: str
    ocr_used: bool
    blocks: list[DoclingBlock]
    extracted_char_count: int
    table_block_count: int
    image_block_count: int
    quality_status: str = "pending"
    cache_path: str | None = None
    content_hash: str | None = None
    document_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_type": self.file_type,
            "source_path": self.source_path,
            "title": self.title,
            "parser_name": self.parser_name,
            "ocr_used": self.ocr_used,
            "blocks": [block.to_dict() for block in self.blocks],
            "extracted_char_count": self.extracted_char_count,
            "table_block_count": self.table_block_count,
            "image_block_count": self.image_block_count,
            "quality_status": self.quality_status,
            "cache_path": self.cache_path,
            "content_hash": self.content_hash,
            "document_metadata": self.document_metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DoclingDocument:
        return cls(
            file_type=str(payload.get("file_type") or ""),
            source_path=str(payload.get("source_path") or ""),
            title=str(payload.get("title") or ""),
            parser_name=str(payload.get("parser_name") or "unknown"),
            ocr_used=bool(payload.get("ocr_used", False)),
            blocks=[DoclingBlock(**block) for block in payload.get("blocks", [])],
            extracted_char_count=int(payload.get("extracted_char_count") or 0),
            table_block_count=int(payload.get("table_block_count") or 0),
            image_block_count=int(payload.get("image_block_count") or 0),
            quality_status=str(payload.get("quality_status") or "pending"),
            cache_path=str(payload.get("cache_path") or "") or None,
            content_hash=str(payload.get("content_hash") or "") or None,
            document_metadata=dict(payload.get("document_metadata") or {}),
        )


@dataclass(slots=True)
class ChunkBuildResult:
    chunks: list[dict[str, Any]]
    document_metadata: dict[str, Any]


def get_document_parser_capabilities() -> dict[str, bool]:
    runtime_ready = is_docling_runtime_available()
    pdf_runtime_ready = is_docling_pdf_runtime_available()
    capabilities: dict[str, bool] = {}
    for file_type in get_ingestion_supported_file_types():
        capabilities[file_type] = pdf_runtime_ready if file_type == "pdf" else runtime_ready
    return capabilities


def is_ingestion_file_type_supported(file_type: str) -> bool:
    return get_document_parser_capabilities().get(str(file_type).lower(), False)


def get_missing_document_parser_types(allowed_types: list[str] | None = None) -> list[str]:
    capabilities = get_document_parser_capabilities()
    target_types = allowed_types or list(get_ingestion_supported_file_types())
    return [file_type for file_type in target_types if not capabilities.get(file_type, False)]


def get_document_runtime_readiness(allowed_types: list[str] | None = None) -> dict[str, Any]:
    capabilities = get_document_parser_capabilities()
    target_types = allowed_types or list(get_ingestion_supported_file_types())
    missing_types = [file_type for file_type in target_types if not capabilities.get(file_type, False)]
    return {
        "docling_runtime_ready": is_docling_runtime_available(),
        "docling_pdf_runtime_ready": is_docling_pdf_runtime_available(),
        "docling_parser_ready": not missing_types,
        "supported_file_types": target_types,
        "blocked_file_types": ["doc", "ppt"],
        "missing_types": missing_types,
    }


def parse_document_artifact(file_path: str, file_type: str) -> DoclingDocument:
    normalized_type = str(file_type).lower()
    if normalized_type not in set(get_ingestion_supported_file_types()):
        raise ValueError(f"Unsupported file type: {file_type}")
    if normalized_type == "pdf" and not is_docling_pdf_runtime_available():
        raise RuntimeError(
            "Real upstream Docling PDF runtime is not available. PDF remains blocked until the Docling PDF stack is provisioned."
        )
    if normalized_type != "pdf" and not is_docling_runtime_available():
        raise RuntimeError(
            "Real upstream Docling runtime is not available. Supported non-PDF formats remain blocked until Docling is installed."
        )
    path = Path(file_path)
    content_hash = _hash_file(path)
    cache_signature_payload = json.dumps(
        {
            "content_hash": content_hash,
            "parser_version": PARSER_VERSION,
            "chunker_version": CHUNKER_VERSION,
            "cleaning_profile": CLEANING_PROFILE_ID,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    cache_key = hashlib.sha256(cache_signature_payload.encode("utf-8")).hexdigest()
    cache_path = _CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        document = _build_document_from_upstream_payload(
            payload=cached,
            file_type=normalized_type,
            source_path=path,
            cache_path=cache_path,
            content_hash=content_hash,
        )
        return document

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = _convert_source_to_upstream_docling_payload(path, normalized_type)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    document = _build_document_from_upstream_payload(
        payload=payload,
        file_type=normalized_type,
        source_path=path,
        cache_path=cache_path,
        content_hash=content_hash,
    )
    return document


def parse_document_sections(file_path: str, file_type: str) -> list[ParsedSection]:
    document = parse_document_artifact(file_path, file_type)
    return [
        ParsedSection(
            text=block.text,
            metadata={
                **block.metadata,
                "block_id": block.block_id,
                "block_type": block.block_type,
                "heading_path": block.heading_path,
                "docling_group_type": block.anchor_group_type,
                "docling_group_id": block.anchor_group_id,
                "provenance": block.provenance,
                "caption": block.caption,
                "parser_name": document.parser_name,
                "ocr_used": document.ocr_used,
                "cache_path": document.cache_path,
                "document_title": document.title,
            },
        )
        for block in document.blocks
        if block.text.strip()
    ]


def build_chunk_bundle(*, file_type: str, document: DoclingDocument) -> ChunkBuildResult:
    upstream_document = _load_upstream_docling_document(document)
    if upstream_document is None:
        raise RuntimeError("Docling chunking requires a persisted upstream Docling JSON artifact")

    ensure_docling_runtime_on_path()
    from docling.chunking import HybridChunker

    chunker = HybridChunker(tokenizer=_make_static_tokenizer(max_tokens=_MAX_SECTION_TOKENS))
    chunks: list[dict[str, Any]] = []
    for chunk_index, chunk in enumerate(chunker.chunk(upstream_document)):
        payload = _docling_chunk_to_payload(
            document=document,
            upstream_document=upstream_document,
            chunk=chunk,
            chunk_index=chunk_index,
            chunker=chunker,
        )
        if payload is not None:
            chunks.append(payload)

    table_blocks = [block for block in document.blocks if block.block_type == "table"]
    table_chunks: list[dict[str, Any]] = []
    for block in table_blocks:
        table_chunks.extend(_build_docling_table_chunks(document=document, block=block, start_index=len(chunks) + len(table_chunks)))
    if table_chunks:
        chunks = [chunk for chunk in chunks if str(chunk.get("metadata_json", {}).get("block_type") or "") != "table"]
        chunks.extend(table_chunks)

    _mark_duplicate_chunks(chunks)
    return ChunkBuildResult(chunks=chunks, document_metadata=_build_document_metrics(document, chunks))


def is_generated_preview_supported(file_type: str) -> bool:
    return str(file_type or "").lower() in _PREVIEW_GENERATED_TYPES


def build_preview_html_artifact(*, document: DoclingDocument, max_chars: int = 120_000) -> str:
    """Build a lightweight structured HTML preview from parsed document blocks."""
    groups: list[tuple[str, list[str]]] = []
    current_group_label = _preview_group_label(document.file_type)
    current_group_blocks: list[str] = []
    list_buffer: list[str] = []
    consumed = 0
    truncated = False

    def flush_list_buffer() -> None:
        nonlocal list_buffer
        if not list_buffer:
            return
        current_group_blocks.append(f"<ul class='preview-list'>{''.join(list_buffer)}</ul>")
        list_buffer = []

    def flush_group() -> None:
        if not current_group_blocks and not list_buffer:
            return
        flush_list_buffer()
        groups.append((current_group_label, list(current_group_blocks)))
        current_group_blocks.clear()

    for block in document.blocks:
        block_text = _normalize_text(str(getattr(block, "text", "") or ""))
        if not block_text:
            continue

        next_group_label = _preview_group_label_for_block(document.file_type, block)
        if next_group_label != current_group_label:
            flush_group()
            current_group_label = next_group_label

        block_markup, consumed_delta, block_truncated = _render_preview_block(block=block, remaining=max_chars - consumed)
        if not block_markup:
            if block_truncated:
                truncated = True
                break
            continue

        block_type = str(getattr(block, "block_type", "paragraph") or "paragraph").lower()
        if block_type == "list":
            list_buffer.append(block_markup)
        else:
            flush_list_buffer()
            current_group_blocks.append(block_markup)

        consumed += consumed_delta
        if block_truncated:
            truncated = True
            break

    flush_group()

    if not groups:
        groups = [(_preview_group_label(document.file_type), ["<p class='preview-empty'>文档内容为空或无法提取可预览文本。</p>"])]

    if truncated and groups:
        groups[-1][1].append("<p class='preview-note'>内容较长，当前仅展示前部预览，请使用“新窗口打开”查看完整原文或预览文件。</p>")

    escaped_title = html.escape(document.title or "Document Preview")
    escaped_parser = html.escape(document.parser_name or "unknown")
    escaped_file_type = html.escape((document.file_type or "unknown").upper())
    escaped_quality = html.escape(document.quality_status or "unknown")
    escaped_preview_mode = html.escape(_preview_group_label(document.file_type))
    rendered_groups = "".join(
        (
            "<section class='preview-sheet'>"
            "<div class='sheet-header'>"
            f"<span>{html.escape(label)}</span>"
            "</div>"
            f"<div class='sheet-body'>{''.join(items)}</div>"
            "</section>"
        )
        for label, items in groups
    )
    return (
        "<!doctype html>"
        "<html lang='zh-CN'>"
        "<head>"
        "<meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        f"<title>{escaped_title}</title>"
        "<style>"
        ":root{color-scheme:light;}"
        "*{box-sizing:border-box;}"
        "body{margin:0;background:#f3f4f6;color:#0f172a;font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}"
        ".layout{min-height:100vh;padding:24px 20px 40px;}"
        ".preview-shell{max-width:1120px;margin:0 auto;}"
        ".hero{position:sticky;top:0;z-index:5;margin-bottom:18px;border:1px solid #dbe3f0;border-radius:18px;background:rgba(255,255,255,.92);backdrop-filter:blur(14px);box-shadow:0 10px 25px rgba(15,23,42,.08);padding:18px 20px;}"
        ".hero h1{margin:0;font-size:20px;line-height:1.4;}"
        ".hero-subtitle{margin:6px 0 0;color:#64748b;font-size:13px;line-height:1.6;}"
        ".hero-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}"
        ".chip{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:#eef2ff;color:#4338ca;font-size:12px;font-weight:600;}"
        ".preview-sheet{max-width:980px;margin:0 auto 18px;background:#fff;border:1px solid #dbe3f0;border-radius:22px;box-shadow:0 14px 34px rgba(15,23,42,.08);overflow:hidden;}"
        ".sheet-header{display:flex;align-items:center;justify-content:space-between;padding:12px 18px;border-bottom:1px solid #e5e7eb;background:linear-gradient(180deg,#f8fafc,#f1f5f9);font-size:12px;font-weight:700;color:#475569;letter-spacing:.04em;text-transform:uppercase;}"
        ".sheet-body{padding:22px 24px 28px;}"
        ".preview-heading{margin:0 0 14px;line-height:1.45;color:#0f172a;}"
        ".preview-heading.level-1{font-size:28px;}"
        ".preview-heading.level-2{font-size:24px;}"
        ".preview-heading.level-3{font-size:20px;}"
        ".preview-heading.level-4,.preview-heading.level-5,.preview-heading.level-6{font-size:18px;}"
        ".preview-path,.preview-block-meta,.preview-table-caption,.preview-note{margin:0 0 10px;color:#64748b;font-size:12px;line-height:1.6;}"
        ".preview-path{font-weight:600;letter-spacing:.01em;}"
        ".preview-paragraph,.preview-empty{margin:0 0 16px;font-size:15px;line-height:1.85;white-space:pre-wrap;word-break:break-word;color:#1e293b;}"
        ".preview-list{margin:0 0 18px;padding-left:22px;color:#1e293b;}"
        ".preview-list li{margin:0 0 8px;line-height:1.8;}"
        ".preview-table-card{margin:0 0 18px;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;background:#fff;}"
        ".preview-table-scroll{overflow:auto;}"
        ".preview-table{width:100%;border-collapse:collapse;min-width:480px;}"
        ".preview-table thead th{padding:10px 12px;border-bottom:1px solid #dbe3f0;background:#f8fafc;font-size:13px;font-weight:700;color:#334155;text-align:left;vertical-align:top;}"
        ".preview-table tbody td{padding:10px 12px;border-top:1px solid #eef2f7;font-size:13px;line-height:1.75;color:#1e293b;vertical-align:top;white-space:pre-wrap;word-break:break-word;}"
        ".preview-table-card .preview-block-meta{padding:0 14px 14px;margin:0;}"
        "@media (max-width: 768px){.layout{padding:16px 12px 28px;}.hero{position:static;padding:16px;}.sheet-body{padding:18px 16px 22px;}.preview-heading.level-1{font-size:22px;}.preview-heading.level-2{font-size:20px;}}"
        "</style>"
        "</head>"
        "<body>"
        "<div class='layout'>"
        "<div class='preview-shell'>"
        "<header class='hero'>"
        f"<h1>{escaped_title}</h1>"
        f"<p class='hero-subtitle'>{escaped_preview_mode}</p>"
        "<div class='hero-meta'>"
        f"<span class='chip'>类型 {escaped_file_type}</span>"
        f"<span class='chip'>Parser {escaped_parser}</span>"
        f"<span class='chip'>Blocks {len(document.blocks)}</span>"
        f"<span class='chip'>状态 {escaped_quality}</span>"
        "</div>"
        "</header>"
        f"{rendered_groups}"
        "</div>"
        "</div>"
        "</body>"
        "</html>"
    )


def _preview_group_label(file_type: str) -> str:
    normalized = str(file_type or "").lower()
    if normalized == "pptx":
        return "结构化幻灯片预览"
    return "结构化文档预览"


def _preview_group_label_for_block(file_type: str, block: DoclingBlock) -> str:
    provenance = block.provenance or {}
    if file_type == "pptx":
        slide_no = provenance.get("slide_number") or provenance.get("page_number")
        if slide_no is not None:
            return f"第 {int(slide_no)} 张幻灯片"
    page_no = provenance.get("page_number")
    if page_no is not None:
        return f"第 {int(page_no)} 页"
    return _preview_group_label(file_type)


def _render_preview_block(*, block: DoclingBlock, remaining: int) -> tuple[str, int, bool]:
    if remaining <= 0:
        return "", 0, True

    block_type = str(block.block_type or "paragraph").lower()
    if block_type == "table":
        return _render_preview_table_block(block=block, remaining=remaining)

    block_text = _normalize_text(str(block.text or ""))
    if not block_text:
        return "", 0, False

    rendered_text, consumed, truncated = _truncate_preview_text(block_text, remaining)
    if not rendered_text:
        return "", 0, truncated

    path_markup = _render_preview_path(block)
    provenance_markup = _render_preview_provenance(block)

    if block_type == "heading":
        level = min(max(len(block.heading_path), 1), 6)
        markup = (
            f"{path_markup}<h2 class='preview-heading level-{level}'>{html.escape(rendered_text)}</h2>{provenance_markup}"
        )
        return markup, consumed, truncated

    if block_type == "list":
        list_text = rendered_text.lstrip("-*• ").strip() or rendered_text
        markup = f"<li>{html.escape(list_text)}</li>"
        return markup, consumed, truncated

    markup = (
        f"{path_markup}<p class='preview-paragraph'>{html.escape(rendered_text)}</p>{provenance_markup}"
    )
    return markup, consumed, truncated


def _render_preview_table_block(*, block: DoclingBlock, remaining: int) -> tuple[str, int, bool]:
    caption = _normalize_text(str(block.caption or ""))
    table_meta = dict(block.metadata or {})
    headers = [str(value).strip() for value in table_meta.get("headers") or []]
    rows = [
        [str(cell).strip() for cell in row]
        for row in table_meta.get("rows") or []
        if isinstance(row, list | tuple)
    ]

    text_budget = max(0, remaining)
    caption_rendered, caption_chars, caption_truncated = _truncate_preview_text(caption, text_budget)
    consumed = caption_chars
    remaining_after_caption = max(0, remaining - consumed)

    header_cells: list[str] = []
    header_consumed = 0
    header_truncated = False
    if headers:
        for header in headers:
            if remaining_after_caption - header_consumed <= 0:
                header_truncated = True
                break
            header_text, delta, is_truncated = _truncate_preview_text(header, remaining_after_caption - header_consumed)
            if not header_text:
                header_truncated = header_truncated or is_truncated
                break
            header_cells.append(header_text)
            header_consumed += delta
            if is_truncated:
                header_truncated = True
                break
    consumed += header_consumed

    body_rows: list[list[str]] = []
    remaining_after_headers = max(0, remaining - consumed)
    row_truncated = caption_truncated or header_truncated
    for row in rows:
        rendered_row: list[str] = []
        row_chars = 0
        for cell in row:
            available = remaining_after_headers - row_chars
            if available <= 0:
                row_truncated = True
                break
            cell_text, delta, is_truncated = _truncate_preview_text(cell, available)
            if not cell_text and is_truncated:
                row_truncated = True
                break
            rendered_row.append(cell_text)
            row_chars += delta
            if is_truncated:
                row_truncated = True
                break
        if rendered_row:
            body_rows.append(rendered_row)
            consumed += row_chars
            remaining_after_headers = max(0, remaining - consumed)
        if row_truncated or remaining_after_headers <= 0:
            break

    if not header_cells and not body_rows and not caption_rendered:
        return "", consumed, True

    path_markup = _render_preview_path(block)
    caption_markup = f"<p class='preview-table-caption'>{html.escape(caption_rendered)}</p>" if caption_rendered else ""
    table_head = (
        "<thead><tr>"
        + "".join(f"<th>{html.escape(cell)}</th>" for cell in header_cells)
        + "</tr></thead>"
        if header_cells
        else ""
    )
    table_body = (
        "<tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
            for row in body_rows
        )
        + "</tbody>"
        if body_rows
        else ""
    )
    if not table_head and not table_body:
        return "", consumed, True
    provenance_markup = _render_preview_provenance(block, suffix="表格")
    markup = (
        f"{path_markup}<figure class='preview-table-card'>{caption_markup}"
        "<div class='preview-table-scroll'>"
        f"<table class='preview-table'>{table_head}{table_body}</table>"
        "</div>"
        f"{provenance_markup}</figure>"
    )
    return markup, consumed, row_truncated


def _truncate_preview_text(text: str, remaining: int) -> tuple[str, int, bool]:
    normalized = _normalize_text(text)
    if not normalized:
        return "", 0, False
    if remaining <= 0:
        return "", 0, True
    if len(normalized) <= remaining:
        return normalized, len(normalized), False
    trimmed = normalized[: max(0, remaining - 1)].rstrip()
    if not trimmed:
        return "", 0, True
    return f"{trimmed}…", len(trimmed), True


def _render_preview_path(block: DoclingBlock) -> str:
    heading_path = [part.strip() for part in block.heading_path[:-1] if str(part or "").strip()]
    if not heading_path:
        return ""
    return f"<p class='preview-path'>{html.escape(' / '.join(heading_path))}</p>"


def _render_preview_provenance(block: DoclingBlock, *, suffix: str | None = None) -> str:
    provenance = block.provenance or {}
    labels: list[str] = []
    slide_no = provenance.get("slide_number")
    page_no = provenance.get("page_number")
    if slide_no is not None:
        labels.append(f"第 {int(slide_no)} 张幻灯片")
    elif page_no is not None:
        labels.append(f"第 {int(page_no)} 页")
    if suffix:
        labels.append(suffix)
    if not labels:
        return ""
    return f"<p class='preview-block-meta'>{html.escape(' · '.join(labels))}</p>"


def build_chunk_payloads(
    *,
    file_type: str,
    sections: list[ParsedSection],
    chunk_size_text: int,
    chunk_overlap_text: int,
    chunk_size_markdown: int,
    chunk_overlap_markdown: int,
) -> list[dict[str, Any]]:
    _ = (chunk_size_text, chunk_overlap_text, chunk_size_markdown, chunk_overlap_markdown)
    payloads: list[dict[str, Any]] = []
    for index, section in enumerate(sections):
        content = str(section.text or "").strip()
        if not content:
            continue
        metadata = dict(section.metadata or {})
        metadata.setdefault("file_type", file_type)
        metadata.setdefault("char_count", len(content))
        metadata.setdefault("line_count", content.count("\n") + 1)
        metadata.setdefault("token_count", _estimate_token_count(content))
        metadata.setdefault("approx_token_count", metadata["token_count"])
        metadata.setdefault("quality_status", "ok")
        payloads.append({"chunk_index": index, "content": content, "metadata_json": metadata})
    return payloads


def _make_static_tokenizer(max_tokens: int) -> Any:
    from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer

    class _StaticApproxTokenizer(BaseTokenizer):
        max_tokens: int

        def count_tokens(self, text: str) -> int:
            return _estimate_token_count(text)

        def get_max_tokens(self) -> int:
            return self.max_tokens

        def get_tokenizer(self) -> None:
            return None

    return _StaticApproxTokenizer(max_tokens=max_tokens)


def _load_upstream_docling_document(document: DoclingDocument) -> Any | None:
    cache_path = Path(str(document.cache_path or ""))
    if not cache_path.exists():
        return None

    ensure_docling_runtime_on_path()
    from docling_core.types.doc import DoclingDocument as UpstreamDoclingDocument

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    return UpstreamDoclingDocument.model_validate(payload)


def _docling_chunk_to_payload(
    *,
    document: DoclingDocument,
    upstream_document: Any,
    chunk: Any,
    chunk_index: int,
    chunker: Any,
) -> dict[str, Any] | None:
    text = str(getattr(chunk, "text", "") or "").strip()
    if not text:
        return None

    doc_items = list(getattr(getattr(chunk, "meta", None), "doc_items", []) or [])
    headings = [str(item) for item in list(getattr(getattr(chunk, "meta", None), "headings", []) or []) if item]
    captions = [str(item) for item in list(getattr(getattr(chunk, "meta", None), "captions", []) or []) if item]
    provenance = _docling_chunk_provenance(doc_items, document.file_type)
    block_type = _docling_chunk_block_type(doc_items)
    anchor_group_id = _docling_chunk_group_id(doc_items, block_type, chunk_index)
    group_type = "table" if block_type == "table" else "section"
    contextualized = str(chunker.contextualize(chunk)).strip()
    metadata = {
        "file_type": document.file_type,
        "parser_name": document.parser_name,
        "ocr_used": document.ocr_used,
        "heading_path": headings,
        "block_type": block_type,
        "docling_group_type": group_type,
        "docling_group_id": anchor_group_id,
        "docling_item_refs": [str(getattr(item, "self_ref", "") or "") for item in doc_items if getattr(item, "self_ref", None)],
        "chunker_type": "docling_hybrid",
        "token_count": _estimate_token_count(contextualized),
        "char_count": len(text),
        "line_count": text.count("\n") + 1,
        "provenance": provenance,
        "quality_status": "ok",
        "contextualized_text": contextualized,
        "document_title": document.title,
    }
    if captions:
        metadata["caption"] = captions[0]
    if provenance:
        first = provenance[0]
        if "page_number" in first:
            metadata["page_number"] = first["page_number"]
        if "slide_number" in first:
            metadata["slide_number"] = first["slide_number"]
    if block_type == "table":
        metadata["table_header"] = ""
        metadata["table_row_count"] = _docling_chunk_table_row_count(doc_items)
        metadata["table_id"] = anchor_group_id
    return {"chunk_index": chunk_index, "content": text, "metadata_json": metadata, "embedding_input": contextualized}


def _build_docling_table_chunks(document: DoclingDocument, block: DoclingBlock, *, start_index: int) -> list[dict[str, Any]]:
    headers = [str(item).strip() for item in list(block.metadata.get("headers") or []) if str(item).strip()]
    rows = [list(row) for row in list(block.metadata.get("rows") or [])]
    caption = str(block.caption or "").strip() or (block.heading_path[-1] if block.heading_path else "")
    if not headers and not rows:
        return []

    header_line = " | ".join(headers)
    chunks: list[dict[str, Any]] = []
    chunk_rows: list[list[str]] = []
    for row in rows or [[]]:
        prospective = [*chunk_rows, row]
        prospective_text = _build_table_content(caption, header_line, prospective)
        if chunk_rows and _estimate_token_count(prospective_text) > _MAX_TABLE_TOKENS:
            chunks.append(
                _build_docling_table_chunk(
                    document=document,
                    block=block,
                    header_line=header_line,
                    caption=caption,
                    rows=chunk_rows,
                    chunk_index=start_index + len(chunks),
                )
            )
            chunk_rows = []
        chunk_rows.append(row)
    if chunk_rows:
        chunks.append(
            _build_docling_table_chunk(
                document=document,
                block=block,
                header_line=header_line,
                caption=caption,
                rows=chunk_rows,
                chunk_index=start_index + len(chunks),
            )
        )
    return chunks


def _build_docling_table_chunk(
    *,
    document: DoclingDocument,
    block: DoclingBlock,
    header_line: str,
    caption: str,
    rows: list[list[str]],
    chunk_index: int,
) -> dict[str, Any]:
    content = _build_table_content(caption, header_line, rows)
    parts = [f"文档标题：{document.title}"] if document.title else []
    if block.heading_path:
        parts.append(f"标题路径：{' > '.join(block.heading_path)}")
    if caption:
        parts.append(f"表标题：{caption}")
    parts.append(content)
    contextualized = "\n".join(parts).strip()
    metadata = {
        "file_type": document.file_type,
        "parser_name": document.parser_name,
        "ocr_used": document.ocr_used,
        "heading_path": list(block.heading_path),
        "block_type": "table",
        "docling_group_type": "table",
        "docling_group_id": block.anchor_group_id,
        "docling_item_refs": [block.block_id],
        "chunker_type": "docling_table",
        "token_count": _estimate_token_count(contextualized),
        "char_count": len(content),
        "line_count": content.count("\n") + 1,
        "provenance": [{**block.provenance, "row_count": len(rows), "chunk_index": chunk_index}],
        "quality_status": "ok",
        "contextualized_text": contextualized,
        "document_title": document.title,
        "caption": caption,
        "table_header": header_line,
        "table_row_count": len(rows),
        "table_id": block.anchor_group_id,
    }
    if "page_number" in block.provenance:
        metadata["page_number"] = block.provenance["page_number"]
    if "slide_number" in block.provenance:
        metadata["slide_number"] = block.provenance["slide_number"]
    return {"chunk_index": chunk_index, "content": content, "metadata_json": metadata, "embedding_input": contextualized}


def _docling_chunk_block_type(doc_items: list[Any]) -> str:
    labels = {_docling_label_value(item) for item in doc_items}
    if "table" in labels:
        return "table"
    if "list_item" in labels:
        return "list"
    if "title" in labels or "section_header" in labels:
        return "heading"
    return "paragraph"


def _docling_chunk_group_id(doc_items: list[Any], block_type: str, chunk_index: int) -> str:
    for item in doc_items:
        self_ref = str(getattr(item, "self_ref", "") or "")
        if self_ref:
            return self_ref
    return f"{block_type}-{chunk_index}"


def _docling_chunk_provenance(doc_items: list[Any], file_type: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in doc_items:
        for prov in list(getattr(item, "prov", []) or []):
            bbox = getattr(prov, "bbox", None)
            page_no = getattr(prov, "page_no", None)
            payload: dict[str, Any] = {"chunk_index": None}
            if page_no is not None:
                payload["page_number"] = int(page_no)
                if file_type == "pptx":
                    payload["slide_number"] = int(page_no)
            if bbox is not None:
                payload["bbox"] = {
                    "l": float(getattr(bbox, "l", 0.0)),
                    "t": float(getattr(bbox, "t", 0.0)),
                    "r": float(getattr(bbox, "r", 0.0)),
                    "b": float(getattr(bbox, "b", 0.0)),
                }
            entries.append(payload)
    return entries


def _docling_chunk_table_row_count(doc_items: list[Any]) -> int:
    for item in doc_items:
        if _docling_label_value(item) == "table":
            data = getattr(item, "data", None)
            if data is not None:
                return int(getattr(data, "num_rows", 0) or 0)
    return 0


def _convert_source_to_upstream_docling_payload(path: Path, file_type: str) -> dict[str, Any]:
    ensure_docling_runtime_on_path()
    if file_type == "pdf":
        return _convert_pdf_source_to_upstream_docling_payload(path)

    from docling.backend.html_backend import HTMLDocumentBackend
    from docling.backend.md_backend import MarkdownDocumentBackend
    from docling.backend.mspowerpoint_backend import MsPowerpointDocumentBackend
    from docling.backend.msword_backend import MsWordDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import InputDocument

    backend_map = {
        "md": (InputFormat.MD, MarkdownDocumentBackend),
        "txt": (InputFormat.MD, MarkdownDocumentBackend),
        "html": (InputFormat.HTML, HTMLDocumentBackend),
        "docx": (InputFormat.DOCX, MsWordDocumentBackend),
        "pptx": (InputFormat.PPTX, MsPowerpointDocumentBackend),
    }
    format_backend = backend_map.get(file_type)
    if format_backend is None:
        raise ValueError(f"Unsupported upstream Docling format: {file_type}")

    input_format, backend_cls = format_backend
    path_or_stream: Path | BytesIO = path
    filename = None
    if file_type == "txt":
        path_or_stream = BytesIO(path.read_bytes())
        filename = path.name

    in_doc = InputDocument(path_or_stream=path_or_stream, format=input_format, backend=backend_cls, filename=filename)
    if not getattr(in_doc, "valid", False) or not getattr(in_doc, "_backend", None):
        raise RuntimeError(f"Upstream Docling backend could not load document {path.name} ({file_type})")

    backend = in_doc._backend
    try:
        doc = backend.convert()
        return cast(dict[str, Any], doc.export_to_dict())
    finally:
        try:
            backend.unload()
        except Exception:
            pass


def _convert_pdf_source_to_upstream_docling_payload(path: Path) -> dict[str, Any]:
    ensure_docling_runtime_on_path()
    from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import InputDocument
    from docling_core.types.doc import DocItemLabel, ProvenanceItem
    from docling_core.types.doc import DoclingDocument as UpstreamDoclingDocument

    in_doc = InputDocument(path_or_stream=path, format=InputFormat.PDF, backend=DoclingParseDocumentBackend)
    if not getattr(in_doc, "valid", False) or not getattr(in_doc, "_backend", None):
        raise RuntimeError(f"Upstream Docling PDF backend could not load document {path.name}")

    backend = in_doc._backend
    doc = UpstreamDoclingDocument(name=path.stem)
    try:
        for page_index in range(backend.page_count()):
            page_backend = backend.load_page(page_index)
            try:
                page_size = page_backend.get_size()
                doc.add_page(page_no=page_index + 1, size=page_size)
                for cell in list(page_backend.get_text_cells()):
                    text = _normalize_text(str(getattr(cell, "text", "") or ""))
                    if not text:
                        continue
                    bbox = cell.rect.to_bounding_box() if hasattr(cell.rect, "to_bounding_box") else None
                    prov = None
                    if bbox is not None:
                        prov = ProvenanceItem(
                            page_no=page_index + 1,
                            bbox=bbox,
                            charspan=(0, len(text)),
                        )
                    doc.add_text(
                        label=DocItemLabel.PARAGRAPH,
                        text=text,
                        orig=text,
                        prov=prov,
                    )
            finally:
                try:
                    page_backend.unload()
                except Exception:
                    pass
        return cast(dict[str, Any], doc.export_to_dict())
    finally:
        try:
            backend.unload()
        except Exception:
            pass


def _build_document_from_upstream_payload(
    *,
    payload: dict[str, Any],
    file_type: str,
    source_path: Path,
    cache_path: Path,
    content_hash: str,
) -> DoclingDocument:
    from importlib.metadata import version as package_version

    from docling_core.types.doc import (
        ContentLayer,
    )
    from docling_core.types.doc import (
        DoclingDocument as UpstreamDoclingDocument,
    )
    from docling_core.types.doc import (
        ListItem as UpstreamListItem,
    )
    from docling_core.types.doc import (
        SectionHeaderItem as UpstreamSectionHeaderItem,
    )
    from docling_core.types.doc import (
        TableItem as UpstreamTableItem,
    )
    from docling_core.types.doc import (
        TitleItem as UpstreamTitleItem,
    )

    upstream_doc = UpstreamDoclingDocument.model_validate(payload)
    parser_name = f"upstream_docling:{package_version('docling')}"
    blocks: list[DoclingBlock] = []
    heading_stack: list[str] = []
    section_counter = 0
    list_counter = 0
    table_counter = 0
    active_list_group_id: str | None = None
    previous_was_list = False

    for item, _level in upstream_doc.iterate_items(
        with_groups=False,
        traverse_pictures=False,
        included_content_layers={ContentLayer.BODY},
    ):
        label = _docling_label_value(item)

        if isinstance(item, (UpstreamTitleItem, UpstreamSectionHeaderItem)) or label in {"title", "section_header"}:
            text = _normalize_text(_docling_text(item))
            if not text:
                continue
            level = 1 if isinstance(item, UpstreamTitleItem) or label == "title" else max(1, int(getattr(item, "level", 1) or 1))
            while len(heading_stack) >= level:
                heading_stack.pop()
            heading_stack.append(text)
            section_counter += 1
            active_list_group_id = None
            previous_was_list = False
            blocks.append(
                DoclingBlock(
                    block_id=f"{file_type}-heading-{section_counter}",
                    block_type="heading",
                    text=text,
                    heading_path=list(heading_stack),
                    anchor_group_type="section",
                    anchor_group_id=f"section-{section_counter}",
                    provenance=_docling_provenance(item, file_type=file_type),
                    metadata={"docling_label": label},
                )
            )
            continue

        if isinstance(item, UpstreamTableItem) or label == "table":
            table_counter += 1
            active_list_group_id = None
            previous_was_list = False
            headers, rows = _docling_table_rows(item, upstream_doc)
            caption = _normalize_text(_docling_table_caption(item, upstream_doc))
            blocks.append(
                _build_table_block(
                    prefix=file_type,
                    index=table_counter,
                    heading_path=list(heading_stack),
                    caption=caption,
                    headers=headers,
                    rows=rows,
                    provenance=_docling_provenance(item, file_type=file_type),
                    anchor_group_type="table",
                    anchor_group_id=str(getattr(item, "self_ref", "") or f"table-{table_counter}"),
                )
            )
            continue

        text = _normalize_text(_docling_text(item))
        if not text:
            previous_was_list = False
            active_list_group_id = None
            continue

        if isinstance(item, UpstreamListItem) or label == "list_item":
            if not previous_was_list:
                list_counter += 1
                active_list_group_id = f"list-{list_counter}"
            previous_was_list = True
            list_text = text if text.startswith(("-", "*", "•")) else f"- {text}"
            blocks.append(
                DoclingBlock(
                    block_id=f"{file_type}-list-{list_counter}-{len(blocks)}",
                    block_type="list",
                    text=list_text,
                    heading_path=list(heading_stack),
                    anchor_group_type="list",
                    anchor_group_id=active_list_group_id or f"list-{list_counter}",
                    provenance=_docling_provenance(item, file_type=file_type),
                    metadata={"items": [text], "docling_label": label},
                )
            )
            continue

        previous_was_list = False
        active_list_group_id = None
        section_id = f"section-{section_counter or 1}"
        blocks.append(
            DoclingBlock(
                block_id=f"{file_type}-paragraph-{len(blocks)}",
                block_type="paragraph",
                text=text,
                heading_path=list(heading_stack),
                anchor_group_type="section",
                anchor_group_id=section_id,
                provenance=_docling_provenance(item, file_type=file_type),
                metadata={"docling_label": label},
            )
        )

    blocks = _clean_blocks(blocks, file_type)
    document = DoclingDocument(
        file_type=file_type,
        source_path=str(source_path),
        title=str(payload.get("name") or source_path.stem),
        parser_name=parser_name,
        ocr_used=bool(payload.get("origin", {}).get("mimetype") == "application/pdf" and file_type == "pdf"),
        blocks=blocks,
        extracted_char_count=sum(len(block.text) for block in blocks),
        table_block_count=sum(1 for block in blocks if block.block_type == "table"),
        image_block_count=len(payload.get("pictures") or []),
        cache_path=str(cache_path),
        content_hash=content_hash,
    )
    document.document_metadata = {
        "parser_name": document.parser_name,
        "ocr_used": document.ocr_used,
        "extracted_char_count": document.extracted_char_count,
        "table_block_count": document.table_block_count,
        "image_block_count": document.image_block_count,
        "cache_path": str(cache_path),
        "content_hash": content_hash,
        "quality_status": document.quality_status,
        "parser_version": PARSER_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "cleaning_profile": CLEANING_PROFILE_ID,
        "artifact_schema_name": payload.get("schema_name"),
        "artifact_version": payload.get("version"),
    }
    return document


def _docling_label_value(item: Any) -> str:
    label = getattr(item, "label", None)
    label_value = getattr(label, "value", None)
    if label_value is not None:
        return str(label_value)
    return str(label or item.__class__.__name__).strip().lower()


def _docling_text(item: Any) -> str:
    return str(getattr(item, "text", "") or "").strip()


def _docling_table_caption(item: Any, doc: Any) -> str:
    caption_text = getattr(item, "caption_text", None)
    if callable(caption_text):
        try:
            return str(caption_text(doc) or "")
        except Exception:
            return ""
    return ""


def _docling_table_rows(item: Any, doc: Any) -> tuple[list[str], list[list[str]]]:
    export_to_dataframe = getattr(item, "export_to_dataframe", None)
    if not callable(export_to_dataframe):
        return [], []
    try:
        dataframe = export_to_dataframe(doc)
    except Exception:
        return [], []
    dataframe_columns = getattr(dataframe, "columns", None)
    columns_to_list = getattr(dataframe_columns, "to_list", None)
    if callable(columns_to_list):
        headers = [str(column).strip() for column in columns_to_list()]
    else:
        headers = []
    rows: list[list[str]] = []
    values = getattr(dataframe, "values", None)
    if values is not None:
        for row in values.tolist():
            rows.append([str(cell).strip() for cell in row])
    return headers, rows


def _docling_provenance(item: Any, *, file_type: str) -> dict[str, Any]:
    provenances = list(getattr(item, "prov", []) or [])
    if not provenances:
        return {}
    first = provenances[0]
    page_no = getattr(first, "page_no", None)
    bbox = getattr(first, "bbox", None)
    charspan = getattr(first, "charspan", None)
    payload: dict[str, Any] = {}
    if page_no is not None:
        payload["page_number"] = int(page_no)
        if file_type == "pptx":
            payload["slide_number"] = int(page_no)
    if bbox is not None:
        payload["bbox"] = {
            "l": float(getattr(bbox, "l", 0.0)),
            "t": float(getattr(bbox, "t", 0.0)),
            "r": float(getattr(bbox, "r", 0.0)),
            "b": float(getattr(bbox, "b", 0.0)),
        }
    if charspan is not None:
        payload["charspan"] = [int(value) for value in charspan]
    payload["source_provenance_count"] = len(provenances)
    return payload


def _clean_blocks(blocks: list[DoclingBlock], file_type: str) -> list[DoclingBlock]:
    counts = Counter(_normalize_boundary_line(block.text) for block in blocks if _normalize_boundary_line(block.text))
    repeated_short = {text for text, count in counts.items() if count >= 3 and len(text) <= 40}
    cleaned: list[DoclingBlock] = []
    for block in blocks:
        block.text = _normalize_text(block.text)
        if not block.text:
            continue
        if _looks_like_furniture(block.text, repeated_short):
            continue
        if file_type == "pdf" and _normalize_boundary_line(block.text) in repeated_short:
            continue
        cleaned.append(block)
    return cleaned

def _build_table_content(caption: str, header_line: str, rows: list[list[str]]) -> str:
    parts: list[str] = []
    if caption:
        parts.append(f"表标题：{caption}")
    if header_line:
        parts.append(f"表头：{header_line}")
    for row in rows:
        line = " | ".join(cell for cell in row if cell)
        if line:
            parts.append(f"表行：{line}")
    return "\n".join(parts).strip()


def _build_document_metrics(document: DoclingDocument, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    if not chunks:
        return {**document.document_metadata, "avg_chunk_chars": 0, "short_chunk_ratio": 1.0, "duplicate_chunk_ratio": 0.0, "quality_status": "failed", "chunk_count": 0}
    char_lengths = [len(chunk["content"]) for chunk in chunks]
    short_chunks = [chunk for chunk in chunks if _is_short_chunk(chunk)]
    duplicate_chunks = [chunk for chunk in chunks if chunk["metadata_json"].get("is_duplicate")]
    quality_status = "passed"
    if short_chunks or duplicate_chunks:
        quality_status = "warn"
    return {
        **document.document_metadata,
        "avg_chunk_chars": int(mean(char_lengths)),
        "short_chunk_ratio": round(len(short_chunks) / len(chunks), 4),
        "duplicate_chunk_ratio": round(len(duplicate_chunks) / len(chunks), 4),
        "quality_status": quality_status,
        "chunk_count": len(chunks),
        "title": document.title,
    }


def _mark_duplicate_chunks(chunks: list[dict[str, Any]]) -> None:
    hashes = Counter(_normalized_chunk_hash(chunk["content"]) for chunk in chunks)
    for chunk in chunks:
        chunk_hash = _normalized_chunk_hash(chunk["content"])
        is_duplicate = hashes[chunk_hash] > 1
        chunk["metadata_json"]["is_duplicate"] = is_duplicate
        if is_duplicate:
            chunk["metadata_json"]["quality_status"] = "duplicate"
        elif _is_short_chunk(chunk):
            chunk["metadata_json"]["quality_status"] = "short"

def _build_table_block(
    *,
    prefix: str,
    index: int,
    heading_path: list[str],
    caption: str,
    headers: list[str],
    rows: list[list[str]],
    provenance: dict[str, Any],
    anchor_group_type: str = "table",
    anchor_group_id: str | None = None,
) -> DoclingBlock:
    return DoclingBlock(
        block_id=f"{prefix}-table-{index}",
        block_type="table",
        text=_build_table_content(caption, " | ".join(headers), rows),
        heading_path=heading_path,
        anchor_group_type=anchor_group_type,
        anchor_group_id=anchor_group_id or f"table-{index}",
        provenance=provenance,
        caption=caption or None,
        metadata={"headers": headers, "rows": rows},
    )


def _looks_like_docx_heading_candidate(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    if re.match(r"^第[一二三四五六七八九十0-9]+[章节部分节课篇]\s*", stripped):
        return True
    return bool(
        re.match(r"^(?:[一二三四五六七八九十]+[、.]|\d+(?:\.\d+){1,2})\s*", stripped)
        and len(stripped) <= 40
        and not stripped.endswith((";", "；", "。"))
    )


def _is_short_chunk(chunk: dict[str, Any]) -> bool:
    metadata = chunk["metadata_json"]
    return int(metadata.get("char_count") or 0) < _SHORT_CHUNK_CHAR_THRESHOLD or int(metadata.get("token_count") or 0) < _SHORT_CHUNK_TOKEN_THRESHOLD


def _looks_like_furniture(text: str, repeated_short: set[str]) -> bool:
    collapsed = _normalize_boundary_line(text)
    if collapsed in repeated_short or _PAGE_NUMBER_RE.match(collapsed):
        return True
    if collapsed.startswith(_FURNITURE_PREFIXES):
        return True
    return (len(collapsed) <= 4 and not any(ch.isalnum() for ch in collapsed)) or (
        len(set(collapsed)) == 1 and len(collapsed) >= 3
    )


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _CONTROL_CHAR_RE.sub("", normalized)
    normalized_lines = [_INLINE_SPACE_RE.sub(" ", line).strip() for line in normalized.split("\n")]
    normalized = "\n".join(line for line in normalized_lines if line is not None)
    normalized = _MULTI_BLANK_LINE_RE.sub("\n\n", normalized)
    return normalized.strip()


def _normalize_boundary_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_chunk_hash(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()


def _estimate_token_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, math.ceil(len(stripped) / 4))


def _has_pypdf() -> bool:
    try:
        import pypdf  # noqa: F401
    except Exception:
        return False
    return True


def _has_beautifulsoup() -> bool:
    try:
        import bs4  # noqa: F401
    except Exception:
        return False
    return True
