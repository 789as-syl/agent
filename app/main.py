"""后端应用入口模块: main。"""

import asyncio
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_analytics import admin_analytics_router
from app.api.admin_audit import admin_audit_router
from app.api.admin_operations import admin_operations_router
from app.api.admin_trace_lab import admin_trace_lab_router
from app.api.admin_users import admin_user_router
from app.api.auth import router as auth_router
from app.api.chat_runs import router as chat_runs_router
from app.api.conversations import router as conversations_router
from app.api.health import router as health_router
from app.api.ingestion import admin_ingestion_router
from app.api.learning import learning_router
from app.api.questions import admin_question_router
from app.api.rag_eval_lab import rag_eval_lab_router
from app.core.config import (
    get_ingestion_supported_file_types,
    is_docling_pdf_runtime_available,
    is_docling_runtime_available,
    settings,
)
from app.core.exceptions import (
    AppError,
    app_error_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.core.log_config import get_logger, setup_logging
from app.core.middleware import RateLimitMiddleware, RequestIDMiddleware, SSEConnectionLimitMiddleware

logger = get_logger(__name__)

if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    setup_logging()
    logger.info("Application starting up")

    from app.models import init_db

    await init_db()
    logger.info("Database connection initialized")

    from app.core.schema_guard import ensure_database_schema_current

    await ensure_database_schema_current()
    logger.info("Database schema revision validated")

    from app.core.redis import init_redis

    await init_redis()
    logger.info("Redis connection initialized")

    from app.core.minio import init_minio

    await init_minio()
    logger.info("MinIO client initialized")

    import dashscope

    dashscope.api_key = settings.dashscope_api_key

    if not settings.dashscope_api_key:
        logger.warning("DASHSCOPE_API_KEY is not set. Embedding tasks will fail.")
    from app.core.langsmith import configure_langsmith
    from app.services.document_processing import get_document_runtime_readiness

    if configure_langsmith():
        logger.info("LangSmith tracing enabled")

    supported_types = list(get_ingestion_supported_file_types())
    readiness = get_document_runtime_readiness(supported_types)
    missing_types = list(readiness.get("missing_types") or [])
    docling_runtime_ready = is_docling_runtime_available()
    docling_pdf_runtime_ready = is_docling_pdf_runtime_available()
    if missing_types or not docling_runtime_ready:
        logger.warning(
            "Document parser dependencies are incomplete",
            missing_types=",".join(sorted(missing_types)),
            docling_runtime_ready=docling_runtime_ready,
            docling_pdf_runtime_ready=docling_pdf_runtime_ready,
            supported_types=",".join(supported_types),
        )

    from app.agents.runtime.native_checkpoint import (
        CheckpointRuntimeCompatibilityError,
        get_native_checkpointer,
    )

    try:
        await get_native_checkpointer()
        logger.info("Native LangGraph checkpointer initialized")
    except CheckpointRuntimeCompatibilityError as exc:
        logger.warning("Native LangGraph checkpointer disabled for this runtime", error=str(exc))

    yield

    logger.info("Application shutting down")

    from app.agents.runtime.native_checkpoint import close_native_checkpointer
    from app.core.redis import close_redis
    from app.models import close_db

    await close_native_checkpointer()
    await close_redis()
    await close_db()
    logger.info("All shared resources closed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    from app.models import init_db_engine

    init_db_engine()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SSEConnectionLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)

    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    app.include_router(chat_runs_router, prefix="/api/v1")
    app.include_router(learning_router)
    app.include_router(admin_ingestion_router)
    app.include_router(admin_question_router)
    app.include_router(admin_analytics_router)
    app.include_router(admin_user_router)
    app.include_router(admin_trace_lab_router)
    app.include_router(admin_operations_router)
    app.include_router(rag_eval_lab_router)
    app.include_router(admin_audit_router)

    return app


app = create_app()
