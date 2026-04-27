"""Request tracing, SSE connection limits, and rate limiting middleware."""

import inspect
import re
import time
import uuid
from collections.abc import Awaitable
from http.cookies import SimpleCookie
from typing import Any, ClassVar

from fastapi import status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.log_config import clear_request_id, get_logger, set_request_id
from app.core.redis import redis_client

logger = get_logger(__name__)

ACCESS_COOKIE_NAME = "access_token"
UUID_PATH_SEGMENT_PATTERN = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=/|$)"
)
INTEGER_PATH_SEGMENT_PATTERN = re.compile(r"/\d+(?=/|$)")


def _extract_bearer_token(auth_header: str | None) -> str | None:
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return None


def _extract_access_token_cookie(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None

    cookies = SimpleCookie()
    cookies.load(cookie_header)
    morsel = cookies.get(ACCESS_COOKIE_NAME)
    return morsel.value if morsel else None


def _extract_scope_token(headers: dict[bytes, bytes]) -> str | None:
    auth_header = headers.get(b"authorization", b"").decode("utf-8")
    # EventSource clients often fall back to cookies instead of custom headers.
    return _extract_bearer_token(auth_header) or _extract_access_token_cookie(
        headers.get(b"cookie", b"").decode("utf-8")
    )


def _normalize_rate_limit_path(path: str) -> str:
    # Collapse high-cardinality identifiers into stable templates.
    path = UUID_PATH_SEGMENT_PATTERN.sub("/{id}", path)
    return INTEGER_PATH_SEGMENT_PATTERN.sub("/{id}", path)


async def _resolve_redis_result(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to inject request_id into logging context and response headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Generate or extract request_id
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Set request_id in logging context
        set_request_id(request_id)

        # Log request
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )

        # Process request
        try:
            response: Response = await call_next(request)
            # Add request_id to response headers
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            logger.error("Request failed", error=str(e))
            raise
        finally:
            # Clear context vars
            clear_request_id()


def extract_user_id_from_token(token: str) -> str | None:
    """Extract user_id from JWT token without full validation."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        return str(subject) if subject is not None else None
    except JWTError:
        return None


class SSEConnectionLimitMiddleware:
    """ASGI middleware to limit concurrent SSE connections per user using Redis.

    Features:
    - Distributed connection tracking via Redis
    - User-based limiting (extracted from JWT token)
    - Automatic cleanup on connection close
    - Configurable max connections per user
    - Atomic operations using Lua script to prevent race conditions

    Note: Implemented as a pure ASGI middleware (not BaseHTTPMiddleware)
    to ensure reliable cleanup when SSE connections close.
    """

    MAX_SSE_CONNECTIONS_PER_USER = 3
    CONNECTION_TTL = 3600  # 1 hour TTL for safety cleanup

    # Lua script for atomic check-and-increment
    # Returns: [allowed (0/1), current_count]
    _CHECK_AND_ACQUIRE_SCRIPT = """
    local max_conn = tonumber(ARGV[1])
    local connection_id = ARGV[2]
    local timestamp = tonumber(ARGV[3])
    local ttl = tonumber(ARGV[4])

    -- Clean up old connections first (older than 5 minutes)
    local cleanup_threshold = timestamp - 300
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cleanup_threshold)

    local current = redis.call('ZCARD', KEYS[1])
    if current >= max_conn then
        return {0, current}
    end

    -- Add new connection
    redis.call('ZADD', KEYS[1], timestamp, connection_id)
    redis.call('EXPIRE', KEYS[1], ttl)

    return {1, current + 1}
    """

    _REMOVE_CONNECTION_SCRIPT = """
    redis.call('ZREM', KEYS[1], ARGV[1])
    return 1
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._check_script_sha: str | None = None
        self._remove_script_sha: str | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if "/stream" not in path:
            await self.app(scope, receive, send)
            return

        # Extract token from Authorization header or access-token cookie
        headers = dict(scope.get("headers", []))
        token = _extract_scope_token(headers)

        if not token:
            # If no token found, let the request through (will be handled by auth dependency)
            await self.app(scope, receive, send)
            return

        user_id = extract_user_id_from_token(token)
        if not user_id:
            # If token is invalid, let the request through (will be handled by auth dependency)
            await self.app(scope, receive, send)
            return

        redis_key = f"sse_connections:{user_id}"
        connection_id = str(uuid.uuid4())
        now = time.time()

        try:
            # Load Lua scripts if not already loaded
            if self._check_script_sha is None:
                self._check_script_sha = await _resolve_redis_result(
                    redis_client.script_load(self._CHECK_AND_ACQUIRE_SCRIPT)
                )
            if self._remove_script_sha is None:
                self._remove_script_sha = await _resolve_redis_result(
                    redis_client.script_load(self._REMOVE_CONNECTION_SCRIPT)
                )

            # Atomic check-and-acquire using Lua script
            result = await _resolve_redis_result(
                redis_client.evalsha(
                    self._check_script_sha,
                    1,  # number of keys
                    redis_key,  # KEYS[1]
                    str(self.MAX_SSE_CONNECTIONS_PER_USER),  # ARGV[1]
                    connection_id,  # ARGV[2]
                    str(int(now)),  # ARGV[3]
                    str(self.CONNECTION_TTL),  # ARGV[4]
                )
            )
        except Exception as e:
            logger.error("Redis error in SSE connection limit", error=str(e))
            await self.app(scope, receive, send)
            return

        allowed, current_count = result[0], result[1]

        if not allowed:
            logger.warning(
                "SSE connection limit exceeded",
                user_id=user_id,
                current_connections=current_count,
            )
            response_body = (
                b'{"error_code":"TOO_MANY_SSE_CONNECTIONS",'
                b'"message":"Maximum 3 concurrent SSE connections allowed",'
                b'"details":{"current_connections":'
                + str(current_count).encode()
                + b"}}"
            )
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    [b"content-type", b"application/json"],
                ],
            })
            await send({
                "type": "http.response.body",
                "body": response_body,
            })
            return

        logger.info(
            "SSE connection established",
            user_id=user_id,
            connection_id=connection_id,
            active_connections=current_count,
        )

        try:
            await self.app(scope, receive, send)
        finally:
            try:
                await _resolve_redis_result(
                    redis_client.evalsha(
                        self._remove_script_sha,
                        1,
                        redis_key,
                        connection_id,
                    )
                )
                logger.info(
                    "SSE connection removed",
                    user_id=user_id,
                    connection_id=connection_id,
                )
            except Exception as cleanup_err:
                logger.error(
                    "Failed to cleanup SSE connection",
                    error=str(cleanup_err),
                )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to implement request rate limiting using Redis.

    Features:
    - Distributed rate limiting via Redis
    - User-based limiting (extracted from JWT token)
    - Sliding window algorithm
    - Endpoint-specific rate limits
    - Automatic key expiration
    """

    # Default rate limits (requests per minute)
    DEFAULT_RATE_LIMIT = 60

    # Endpoint-specific rate limits
    ENDPOINT_LIMITS: ClassVar[dict[tuple[str, str], int]] = {
        ("POST", "/api/v1/auth/login"): 8,
        ("POST", "/api/v1/auth/register"): 5,
        ("POST", "/api/v1/conversations/{id}/runs"): 20,  # Chat runs are expensive
        ("POST", "/api/v1/conversations"): 30,
        ("POST", "/api/v1/admin/questions/vectorize"): 10,  # Vectorization trigger only
        ("POST", "/api/v1/admin/uploads"): 20,  # Upload operations
    }

    WINDOW_SIZE = 60  # 1 minute window
    KEY_TTL = 120  # 2 minutes TTL for auto cleanup

    def _get_rate_limit(self, method: str, path: str) -> int:
        normalized_path = _normalize_rate_limit_path(path)
        for (configured_method, path_template), limit in self.ENDPOINT_LIMITS.items():
            if method == configured_method and normalized_path.startswith(path_template):
                return limit
        return self.DEFAULT_RATE_LIMIT

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting only for health probes. Auth endpoints are rate-limited
        # because they are the highest-risk brute-force surface.
        skip_paths = ["/health", "/ready"]
        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)

        # Extract user_id from JWT token
        auth_header = request.headers.get("Authorization", "")
        user_id = None

        token = _extract_bearer_token(auth_header) or request.cookies.get(ACCESS_COOKIE_NAME)
        if token:
            user_id = extract_user_id_from_token(token)

        # Fallback to IP if no valid token
        if not user_id:
            user_id = request.client.host if request.client else "unknown"

        normalized_path = _normalize_rate_limit_path(request.url.path)
        rate_limit = self._get_rate_limit(request.method, request.url.path)

        # Redis key for rate limiting
        now = time.time()
        redis_key = f"rate_limit:{user_id}:{normalized_path}"

        current_count: int | None = None
        try:
            # Use Redis sorted set for sliding window
            window_start = now - self.WINDOW_SIZE

            # Add current request
            request_id = str(uuid.uuid4())
            await redis_client.zadd(redis_key, {request_id: now})
            await redis_client.expire(redis_key, self.KEY_TTL)

            # Remove old requests outside the window
            await redis_client.zremrangebyscore(redis_key, 0, window_start)

            # Get current request count
            current_count = await redis_client.zcard(redis_key)
        except Exception as exc:
            logger.error(
                "Rate limit backend unavailable, bypass rate limiting",
                error=str(exc),
                user_id=user_id,
                path=normalized_path,
            )

        if current_count is not None and current_count > rate_limit:
            logger.warning(
                "Rate limit exceeded",
                user_id=user_id,
                path=normalized_path,
                request_count=current_count,
                limit=rate_limit,
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error_code": "TOO_MANY_REQUESTS",
                    "message": "Rate limit exceeded. Please try again later.",
                    "details": {
                        "limit": rate_limit,
                        "window": f"{self.WINDOW_SIZE} seconds",
                        "current": current_count,
                    },
                },
                headers={
                    "Retry-After": str(self.WINDOW_SIZE),
                    "X-RateLimit-Limit": str(rate_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + self.WINDOW_SIZE)),
                },
            )

        response = await call_next(request)

        if current_count is not None:
            remaining = max(0, rate_limit - current_count)
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(now + self.WINDOW_SIZE))

        return response
