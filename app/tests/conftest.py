"""Shared pytest fixtures for app tests."""

import asyncio
import os
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.models.question_bank import QuestionBank
from app.models.user import User, UserRole, UserStatus

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    settings.database_url
)


def _is_safe_test_database(url: str) -> bool:
    """Guard against truncating developer/production data in tests."""
    if os.getenv("ALLOW_UNSAFE_TEST_DB") == "1" or settings.allow_unsafe_test_db:
        return True

    parsed = urlparse(url)
    db_name = (parsed.path or "").strip("/").lower()
    host = (parsed.hostname or "").lower()

    return "test" in db_name or (host in {"127.0.0.1", "localhost"} and db_name.endswith("_test"))


if settings.database_url == TEST_DATABASE_URL and not _is_safe_test_database(TEST_DATABASE_URL):
    raise RuntimeError(
        "Refusing to run tests against primary DATABASE_URL. "
        "Set TEST_DATABASE_URL to a dedicated test database (recommended *_test). "
        "If you really need this behavior, set ALLOW_UNSAFE_TEST_DB=1 explicitly."
    )


@pytest.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )

    yield engine

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session with transaction rollback for each test."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_session() as session:
        # ⚠️ DISABLED: Reset DB state for deterministic API integration tests.
        # table_names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
        # if table_names:
        #     await session.execute(text(f"TRUNCATE TABLE {table_names} CASCADE"))
        #     await session.commit()

        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with real database session."""

    async def override_get_async_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    from app.models.engine import get_async_session
    app.dependency_overrides[get_async_session] = override_get_async_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def mock_redis() -> Generator[MagicMock, None, None]:
    """Mock Redis client for unit tests."""
    with patch("app.core.redis.redis_client") as mock:
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.ping = AsyncMock(return_value=True)
        mock.exists = AsyncMock(return_value=0)
        yield mock


@pytest.fixture(autouse=True)
def patch_runtime_redis(monkeypatch: MonkeyPatch) -> SimpleNamespace:
    """Use a loop-safe async Redis stub for tests."""
    redis_stub = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
        setex=AsyncMock(return_value=True),
        delete=AsyncMock(return_value=1),
        exists=AsyncMock(return_value=0),
        ping=AsyncMock(return_value=True),
        script_load=AsyncMock(return_value="test-sha"),
        evalsha=AsyncMock(return_value=[1, 1]),
        zadd=AsyncMock(return_value=1),
        expire=AsyncMock(return_value=True),
        zremrangebyscore=AsyncMock(return_value=0),
        zcard=AsyncMock(return_value=0),
    )

    for target in (
        "app.core.redis.redis_client",
        "app.core.middleware.redis_client",
        "app.api.dependencies.redis_client",
        "app.services.admin_analytics_service.redis_client",
        "app.services.ingestion_service.redis_client",
        "app.services.question_service.redis_client",
        "app.services.token_service.redis_client",
    ):
        monkeypatch.setattr(target, redis_stub, raising=False)

    return redis_stub


@pytest.fixture
def mock_minio() -> Generator[MagicMock, None, None]:
    """Mock MinIO client for unit tests."""
    with ExitStack() as stack:
        mock = MagicMock()
        mock.presigned_put_object = MagicMock(return_value="http://minio.test/upload")
        mock.presigned_get_object = MagicMock(return_value="http://minio.test/download")
        mock.bucket_exists = MagicMock(return_value=True)
        mock.make_bucket = MagicMock(return_value=None)
        mock.stat_object = MagicMock(return_value=MagicMock(size=1024))

        for target in (
            "app.core.minio.minio_client",
            "app.services.minio_service.minio_client",
            "app.tasks.ingestion_tasks.minio_client",
        ):
            stack.enter_context(patch(target, mock))

        yield mock


@pytest.fixture
def mock_celery() -> Generator[MagicMock, None, None]:
    """Mock Celery for unit tests."""
    with patch("app.tasks.celery_app.celery_app") as mock:
        mock.send_task = MagicMock(return_value=MagicMock(id="test-task-id"))
        yield mock


@pytest.fixture
def mock_dashscope() -> Generator[MagicMock, None, None]:
    """Mock DashScope API for unit tests."""
    with patch("dashscope.Generation") as mock_gen:
        mock_gen.call = MagicMock(return_value={
            "output": {"text": "Test response"},
            "status_code": 200,
        })
        yield mock_gen


def generate_unique_phone() -> str:
    """Generate a unique phone number for testing (11 digits)."""
    import time
    timestamp_ms = int(time.time() * 1000)
    unique_part = str(timestamp_ms)[-8:]
    return f"139{unique_part}"


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user in database."""
    phone = generate_unique_phone()
    password_hash = hash_password("TestPass123")

    user = User(
        id=uuid4(),
        phone=phone,
        password_hash=password_hash,
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_admin_user(db_session: AsyncSession) -> User:
    """Create a test admin user in database."""
    phone = generate_unique_phone()
    password_hash = hash_password("AdminPass123")

    user = User(
        id=uuid4(),
        phone=phone,
        password_hash=password_hash,
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Create a second regular user for permission and ownership tests."""
    phone = generate_unique_phone()
    password_hash = hash_password("TestPass123")

    user = User(
        id=uuid4(),
        phone=phone,
        password_hash=password_hash,
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_question_bank(db_session: AsyncSession) -> QuestionBank:
    """Create a reusable question bank for repository/service tests."""
    bank = QuestionBank(id=uuid4(), name="Test Bank", description="Test")
    db_session.add(bank)
    await db_session.flush()
    await db_session.refresh(bank)
    return bank


@pytest.fixture
async def auth_headers(client: AsyncClient, test_user: User) -> dict[str, str]:
    """Get authentication headers for test user."""
    from app.services.token_service import TokenService

    tokens = TokenService.generate_tokens(
        user_id=test_user.id,
        phone=test_user.phone,
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
async def admin_auth_headers(client: AsyncClient, test_admin_user: User) -> dict[str, str]:
    """Get authentication headers for admin user."""
    from app.services.token_service import TokenService

    tokens = TokenService.generate_tokens(
        user_id=test_admin_user.id,
        phone=test_admin_user.phone,
    )
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def sample_question_data() -> dict[str, Any]:
    """Sample question data for testing."""
    return {
        "question_text": "What is the capital of France?",
        "question_type": "single",
        "options": [
            {"label": "A", "text": "Paris"},
            {"label": "B", "text": "London"},
            {"label": "C", "text": "Berlin"},
            {"label": "D", "text": "Madrid"},
        ],
        "answer": "A",
        "explanation": "Paris is the capital and largest city of France.",
        "bank_id": str(uuid4()),
        "knowledge_point_ids": [],
    }


@pytest.fixture
def sample_conversation_data() -> dict[str, Any]:
    """Sample conversation data for testing."""
    return {
        "title": "Test Conversation",
    }


@pytest.fixture
def sample_knowledge_point_data() -> dict[str, Any]:
    """Sample knowledge point data for testing."""
    return {
        "title": "Test Knowledge Point",
        "file_type": "pdf",
    }


@pytest.fixture
def mock_sse_stream() -> Callable[[], AsyncGenerator[str, None]]:
    """Mock SSE stream for chat run tests."""
    async def mock_stream() -> AsyncGenerator[str, None]:
        yield 'event: thought\ndata: {"content": "Thinking..."}\n\n'
        yield 'event: tool_call\ndata: {"tool": "retrieval", "input": "test"}\n\n'
        yield 'event: final_answer\ndata: {"answer": "Test answer"}\n\n'

    return mock_stream
