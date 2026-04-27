"""Tests for middleware security helpers."""

from uuid import uuid4

from app.core.middleware import (
    _extract_access_token_cookie,
    _extract_scope_token,
    _normalize_rate_limit_path,
)


def test_extract_access_token_cookie_returns_none_without_cookie() -> None:
    assert _extract_access_token_cookie(None) is None


def test_extract_scope_token_reads_access_cookie() -> None:
    headers = {
        b"cookie": b"session=abc; access_token=cookie-token; theme=dark",
    }

    assert _extract_scope_token(headers) == "cookie-token"


def test_extract_scope_token_prefers_authorization_header() -> None:
    headers = {
        b"authorization": b"Bearer header-token",
        b"cookie": b"access_token=cookie-token",
    }

    assert _extract_scope_token(headers) == "header-token"


def test_normalize_rate_limit_path_replaces_dynamic_segments() -> None:
    path = f"/api/v1/conversations/{uuid4()}/runs/{uuid4()}/stream"

    assert _normalize_rate_limit_path(path) == "/api/v1/conversations/{id}/runs/{id}/stream"


def test_normalize_rate_limit_path_replaces_numeric_segments() -> None:
    path = "/api/v1/admin/items/123/chunks/456"

    assert _normalize_rate_limit_path(path) == "/api/v1/admin/items/{id}/chunks/{id}"
