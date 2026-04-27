"""Unit tests for file signature based upload validation helpers."""

from __future__ import annotations

from io import BytesIO

from app.core.file_signature import detect_file_type, verify_uploaded_file


def test_detect_file_type_returns_cfb_for_legacy_office_magic_bytes() -> None:
    legacy_doc_stream = BytesIO(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest")

    detected = detect_file_type(legacy_doc_stream)

    assert detected == "cfb"


def test_verify_uploaded_file_rejects_docx_content_with_pdf_extension() -> None:
    is_valid, detected_type, error = verify_uploaded_file(
        file_name="notes.pdf",
        file_content=b"PK\x03\x04fake-openxml",
        allowed_extensions={"pdf", "docx"},
    )

    assert is_valid is False
    assert detected_type is None
    assert error == "File content is DOCX, but extension is .pdf, type mismatch"


def test_verify_uploaded_file_rejects_unsafe_extension_even_when_listed_as_allowed() -> None:
    is_valid, detected_type, error = verify_uploaded_file(
        file_name="payload.exe",
        file_content=b"MZ",
        allowed_extensions={"exe", "pdf"},
    )

    assert is_valid is False
    assert detected_type is None
    assert error == "Dangerous file type forbidden from upload: exe"
