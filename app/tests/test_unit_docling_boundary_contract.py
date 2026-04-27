"""Unit tests for Docling hard-cutover boundary helpers."""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_ingestion_supported_file_types
from app.core.file_types import file_name_to_type, normalize_file_type
from app.services import document_processing


def test_settings_enforce_exact_prd_file_type_set() -> None:
    with pytest.raises(ValueError):
        Settings(allowed_file_types="pdf,doc,docx,ppt,pptx,md,html,txt")

    configured = Settings(allowed_file_types="md,html,txt,pdf,docx,pptx")
    assert configured.allowed_file_types == "md,html,txt,pdf,docx,pptx"


def test_settings_require_explicit_jwt_secret_and_cors_in_production() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be explicitly configured"):
        Settings(app_env="production", jwt_secret_key="", cors_origins="https://admin.example.com")

    with pytest.raises(ValueError, match="CORS_ORIGINS must list explicit trusted origins"):
        Settings(app_env="production", jwt_secret_key="x" * 32, cors_origins="*")

    configured = Settings(app_env="production", jwt_secret_key="x" * 32, cors_origins="https://admin.example.com")
    assert configured.cors_origin_list() == ["https://admin.example.com"]


def test_normalize_file_type_rejects_legacy_binary_formats() -> None:
    assert normalize_file_type("application/pdf") == "pdf"
    assert normalize_file_type(".docx") == "docx"
    assert file_name_to_type("demo.pptx") == "pptx"

    with pytest.raises(ValueError):
        normalize_file_type(".doc")
    with pytest.raises(ValueError):
        normalize_file_type("application/msword")
    with pytest.raises(ValueError):
        normalize_file_type(".ppt")

    assert file_name_to_type("legacy.doc") is None
    assert file_name_to_type("legacy.ppt") is None


def test_document_processing_capabilities_follow_docling_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_processing, "is_docling_runtime_available", lambda: False)
    monkeypatch.setattr(document_processing, "is_docling_pdf_runtime_available", lambda: False)

    capabilities = document_processing.get_document_parser_capabilities()

    assert set(capabilities) == set(get_ingestion_supported_file_types())
    assert all(value is False for value in capabilities.values())
    assert document_processing.is_ingestion_file_type_supported("doc") is False
    assert document_processing.is_ingestion_file_type_supported("ppt") is False

    monkeypatch.setattr(document_processing, "is_docling_runtime_available", lambda: True)
    monkeypatch.setattr(document_processing, "is_docling_pdf_runtime_available", lambda: True)
    capabilities = document_processing.get_document_parser_capabilities()
    assert all(value is True for value in capabilities.values())


def test_document_runtime_readiness_reports_supported_and_blocked_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(document_processing, "is_docling_runtime_available", lambda: False)
    monkeypatch.setattr(document_processing, "is_docling_pdf_runtime_available", lambda: False)
    readiness = document_processing.get_document_runtime_readiness()

    assert readiness["docling_runtime_ready"] is False
    assert readiness["docling_pdf_runtime_ready"] is False
    assert readiness["blocked_file_types"] == ["doc", "ppt"]
    assert readiness["supported_file_types"] == list(get_ingestion_supported_file_types())
    assert sorted(readiness["missing_types"]) == sorted(get_ingestion_supported_file_types())
