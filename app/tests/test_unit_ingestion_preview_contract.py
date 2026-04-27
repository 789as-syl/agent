"""Unit tests for preview/source compatibility on ingestion document-url schema."""

from __future__ import annotations

from app.schemas.ingestion import KnowledgePointDocumentUrlResponse


def test_document_url_response_keeps_legacy_url_while_requiring_source_fields() -> None:
    payload = KnowledgePointDocumentUrlResponse(
        url="http://minio.local/source",
        source_url="http://minio.local/source",
        object_path="documents/source.pdf",
        source_object_path="documents/source.pdf",
        file_type="pdf",
        source_file_type="pdf",
        expires_in=3600,
    )

    assert payload.url == "http://minio.local/source"
    assert payload.source_url == "http://minio.local/source"
    assert payload.preview_url is None
    assert payload.preview_available is False


def test_document_url_response_accepts_preview_metadata_fields_when_available() -> None:
    payload = KnowledgePointDocumentUrlResponse(
        url="http://minio.local/compat",
        source_url="http://minio.local/source",
        object_path="documents/source.pdf",
        source_object_path="documents/source.pdf",
        file_type="pdf",
        source_file_type="pdf",
        expires_in=3600,
        preview_url="http://minio.local/preview.pdf",
        preview_object_path="documents/source.preview.pdf",
        preview_file_type="pdf",
        preview_available=True,
        preview_from_source=True,
    )

    assert payload.preview_url == "http://minio.local/preview.pdf"
    assert payload.preview_object_path == "documents/source.preview.pdf"
    assert payload.preview_file_type == "pdf"
    assert payload.preview_available is True
    assert payload.preview_from_source is True
