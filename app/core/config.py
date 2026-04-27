"""Application settings and configuration parsing."""

from __future__ import annotations

import importlib
import secrets
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.docling_runtime import ensure_docling_runtime_on_path

PRD_SUPPORTED_INGESTION_FILE_TYPES: tuple[str, ...] = ("md", "html", "txt", "pdf", "docx", "pptx")
PRD_SUPPORTED_INGESTION_FILE_TYPE_SET = frozenset(PRD_SUPPORTED_INGESTION_FILE_TYPES)
LEGACY_INGESTION_FILE_TYPES = frozenset({"doc", "ppt"})


def get_ingestion_supported_file_types() -> tuple[str, ...]:
    return PRD_SUPPORTED_INGESTION_FILE_TYPES


@lru_cache(maxsize=1)
def is_docling_runtime_available() -> bool:
    try:
        ensure_docling_runtime_on_path()
        importlib.import_module("docling.datamodel.document")
        importlib.import_module("docling.backend.md_backend")
        importlib.import_module("docling.backend.html_backend")
        importlib.import_module("docling.backend.msword_backend")
        importlib.import_module("docling.backend.mspowerpoint_backend")
        importlib.import_module("docling.chunking")
        importlib.import_module("docling_core.types.doc")
    except Exception:
        return False
    return True


@lru_cache(maxsize=1)
def is_docling_pdf_runtime_available() -> bool:
    try:
        ensure_docling_runtime_on_path()
        importlib.import_module("docling.datamodel.document")
        importlib.import_module("docling.backend.docling_parse_backend")
        importlib.import_module("docling_parse")
        importlib.import_module("pypdfium2")
    except Exception:
        return False
    return True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Knowledge Base Agent")
    app_env: str = Field(default="development")
    debug: bool = Field(default=False)
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000, ge=1, le=65535)

    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/knowledge_base")
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=20, ge=0)

    redis_url: str = Field(default="redis://localhost:6379/0")

    minio_endpoint: str = Field(default="localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_secure: bool = Field(default=True)
    minio_bucket_name: str = Field(default="documents")
    minio_max_connections: int = Field(default=10, ge=1, le=100)

    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")
    allow_unsafe_test_db: bool = Field(default=False)

    agent_enabled_tools: str = Field(
        default="knowledge_retrieval,math_calculator",
        description=(
            "Comma-separated tool names to enable for agent runtime. "
            "Web search is intentionally opt-in; set AGENT_ENABLED_TOOLS to include web_search when needed."
        ),
    )
    agent_generation_model: str = Field(default="qwen-turbo")
    agent_generation_temperature: float = Field(default=0.3, ge=0.0, le=1.0)
    agent_generation_max_tokens: int = Field(default=1200, ge=128, le=8192)
    agent_enable_thinking: bool = Field(default=True)
    agent_thinking_budget: int | None = Field(default=None, ge=1, le=65536)
    agent_stream_diagnostics: bool = Field(default=False)
    agent_checkpoint_database_url: str | None = Field(
        default=None,
        description="Optional psycopg/Postgres DSN override for LangGraph durable checkpoints.",
    )
    langsmith_tracing: bool = Field(default=False)
    langsmith_api_key: str = Field(default="")
    langsmith_project: str = Field(default="knowledge-base-agent")
    langsmith_endpoint: str | None = Field(default=None)

    dashscope_api_key: str = Field(default="")
    memory_summary_model: str = Field(default="qwen-turbo")
    memory_summary_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    memory_summary_max_tokens: int = Field(default=800, ge=64, le=4096)
    retrieval_embedding_model: str = Field(default="text-embedding-v3")
    retrieval_embedding_dimension: int = Field(default=1024, ge=1, le=8192)
    retrieval_embedding_batch_size: int = Field(default=10, ge=1, le=64)
    dashscope_embedding_max_batch_size: int = Field(default=10, ge=1, le=64)
    retrieval_rerank_model: str = Field(default="qwen3-rerank")
    retrieval_rerank_top_n: int = Field(default=10, ge=1, le=100)

    jwt_secret_key: str = Field(default="")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_minutes: int = Field(default=1440, ge=1)
    jwt_refresh_expiration_days: int = Field(default=7, ge=1)

    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    max_upload_size: int = Field(default=50 * 1024 * 1024)
    allowed_file_types: str = Field(default="md,html,txt,pdf,docx,pptx")
    ingestion_chunk_size_text: int = Field(default=600, ge=100, le=4000)
    ingestion_chunk_overlap_text: int = Field(default=60, ge=0, le=1000)
    ingestion_chunk_size_markdown: int = Field(default=800, ge=100, le=4000)
    ingestion_chunk_overlap_markdown: int = Field(default=80, ge=0, le=1000)
    ingestion_cache_dir: str = Field(default=".omx/cache/docling")

    bcrypt_work_factor: int = Field(default=12, ge=10, le=16)

    agent_memory_short_window: int = Field(default=12, ge=1, le=100)
    agent_memory_summary_trigger_messages: int = Field(default=8, ge=1, le=100)
    agent_memory_summary_max_chars: int = Field(default=1200, ge=200, le=8000)

    cors_origins: str = Field(default="*")
    admin_analytics_cache_ttl: int = Field(default=60, ge=1, le=3600)
    database_require_head_revision: bool = Field(default=True)

    @model_validator(mode="after")
    def _validate_production_security(self) -> Settings:
        is_production = self.app_env.strip().lower() == "production"
        if not self.jwt_secret_key:
            if is_production:
                raise ValueError(
                    "JWT_SECRET_KEY must be explicitly configured in production. "
                    "Do not rely on a process-local generated secret."
                )
            self.jwt_secret_key = secrets.token_urlsafe(32)

        if is_production and len(self.jwt_secret_key) < 32:
            raise ValueError(
                "JWT secret key must be at least 32 characters with sufficient entropy. "
                "Set JWT_SECRET_KEY environment variable with a secure random value."
            )
        cors_origins = self.cors_origin_list()
        if is_production and (not cors_origins or "*" in cors_origins):
            raise ValueError(
                "CORS_ORIGINS must list explicit trusted origins in production when credentials are enabled."
            )
        return self

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_debug(cls, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return value

    @field_validator("allowed_file_types", mode="before")
    @classmethod
    def _enforce_prd_allowed_file_types(cls, value: Any) -> str:
        raw = str(value or "")
        configured_types = [item.strip().lower().lstrip(".") for item in raw.split(",") if item.strip()]
        if not configured_types:
            configured_types = list(PRD_SUPPORTED_INGESTION_FILE_TYPES)

        configured_set = set(configured_types)
        if configured_set != PRD_SUPPORTED_INGESTION_FILE_TYPE_SET:
            missing = sorted(PRD_SUPPORTED_INGESTION_FILE_TYPE_SET - configured_set)
            unexpected = sorted(configured_set - PRD_SUPPORTED_INGESTION_FILE_TYPE_SET)
            legacy = sorted(configured_set & LEGACY_INGESTION_FILE_TYPES)
            details: list[str] = []
            if missing:
                details.append(f"missing={','.join(missing)}")
            if unexpected:
                details.append(f"unexpected={','.join(unexpected)}")
            if legacy:
                details.append(f"legacy_blocked={','.join(legacy)}")
            detail_suffix = f" ({'; '.join(details)})" if details else ""
            supported = ",".join(PRD_SUPPORTED_INGESTION_FILE_TYPES)
            raise ValueError(f"allowed_file_types must be exactly: {supported}{detail_suffix}")

        return ",".join(PRD_SUPPORTED_INGESTION_FILE_TYPES)


settings = Settings()

