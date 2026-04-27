from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.core.middleware import RateLimitMiddleware


def _build_request(path: str = "/api/v1/conversations") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "root_path": "",
    }
    return Request(scope)


def test_rate_limit_middleware_limits_auth_endpoints() -> None:
    middleware = RateLimitMiddleware(app=AsyncMock())

    assert middleware._get_rate_limit("POST", "/api/v1/auth/login") == 8
    assert middleware._get_rate_limit("POST", "/api/v1/auth/register") == 5
    assert middleware._get_rate_limit("POST", "/api/v1/conversations/00000000-0000-0000-0000-000000000000/runs") == 20


@pytest.mark.asyncio
async def test_rate_limit_middleware_bypasses_when_backend_unavailable() -> None:
    middleware = RateLimitMiddleware(app=AsyncMock())
    request = _build_request()
    call_next = AsyncMock(return_value=Response(status_code=200))

    redis_stub = AsyncMock()
    redis_stub.zadd.side_effect = RuntimeError("redis unavailable")

    with patch("app.core.middleware.redis_client", redis_stub):
        response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
    assert call_next.await_count == 1


@pytest.mark.asyncio
async def test_rate_limit_middleware_does_not_retry_downstream_on_exception() -> None:
    middleware = RateLimitMiddleware(app=AsyncMock())
    request = _build_request()
    call_next = AsyncMock(side_effect=RuntimeError("downstream failed"))

    redis_stub = AsyncMock()
    redis_stub.zadd.return_value = 1
    redis_stub.expire.return_value = True
    redis_stub.zremrangebyscore.return_value = 0
    redis_stub.zcard.return_value = 1

    with (
        patch("app.core.middleware.redis_client", redis_stub),
        pytest.raises(RuntimeError, match="downstream failed"),
    ):
        await middleware.dispatch(request, call_next)

    assert call_next.await_count == 1
