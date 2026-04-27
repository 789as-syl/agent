"""Core helpers for normalized file types and response content types."""

from __future__ import annotations

from app.core.config import get_ingestion_supported_file_types

_MIME_TO_EXT = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/x-markdown": "md",
    "text/html": "html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-word.document.macroenabled.12": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}

_EXT_TO_MIME = {
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_ALIAS_TO_EXT = {
    "markdown": "md",
    "plain": "txt",
    "text": "txt",
    "htm": "html",
}


def normalize_file_type(raw: str) -> str:
    """Normalize extension/mime-style file type into canonical extension."""
    value = (raw or "").strip().lower()
    if not value:
        raise ValueError("file_type is required")

    if ";" in value:
        value = value.split(";", 1)[0].strip()

    if value in _MIME_TO_EXT:
        value = _MIME_TO_EXT[value]

    if "/" in value and value not in _MIME_TO_EXT:
        raise ValueError(f"unsupported file_type: {raw}")

    if value.startswith("."):
        value = value[1:]

    value = _ALIAS_TO_EXT.get(value, value)

    allowed = set(get_ingestion_supported_file_types())
    if value not in allowed:
        raise ValueError(f"unsupported file_type: {raw}")

    return value


def file_name_to_type(file_name: str) -> str | None:
    """Infer normalized file type from file name extension."""
    if "." not in file_name:
        return None
    ext = file_name.rsplit(".", 1)[1].strip().lower()
    if not ext:
        return None
    try:
        return normalize_file_type(ext)
    except ValueError:
        return None


def file_type_to_content_type(raw: str) -> str | None:
    """Map a normalized file type or MIME alias to a response content type."""
    value = (raw or "").strip().lower()
    if not value:
        return None

    if value.startswith("."):
        value = value[1:]

    value = _MIME_TO_EXT[value] if value in _MIME_TO_EXT else _ALIAS_TO_EXT.get(value, value)
    return _EXT_TO_MIME.get(value)
