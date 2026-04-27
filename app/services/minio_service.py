"""Async MinIO helper methods used by ingestion flows."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from app.core.config import settings
from app.core.file_types import file_type_to_content_type
from app.core.minio import minio_client


class MinIOService:
    """Small async facade over the synchronous MinIO SDK."""

    @staticmethod
    async def generate_presigned_url(
        object_path: str,
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned upload URL."""
        url = await asyncio.to_thread(
            minio_client.presigned_put_object,
            bucket_name=settings.minio_bucket_name,
            object_name=object_path,
            expires=timedelta(seconds=expires_in),
        )
        return str(url)

    @staticmethod
    def generate_object_path(file_name: str, file_type: str = "") -> str:
        """Generate a unique, sanitized object path inside the MinIO bucket."""
        unique_id = uuid.uuid4().hex[:8]
        safe_name = MinIOService._sanitize_file_name(file_name, file_type=file_type)
        return f"documents/{unique_id}_{safe_name}"

    @staticmethod
    def generate_preview_object_path(source_object_path: str, *, preview_file_type: str = "html") -> str:
        """Generate a deterministic preview artifact path for a source object."""
        source_name = Path(str(source_object_path or "")).name or "document"
        safe_name = MinIOService._sanitize_file_name(source_name)
        stem = Path(safe_name).stem or "document"
        suffix = preview_file_type.lower().lstrip(".") or "html"
        path_hash = uuid.uuid5(uuid.NAMESPACE_URL, str(source_object_path or "")).hex[:12]
        return f"previews/{path_hash}_{stem}.preview.{suffix}"

    @staticmethod
    def generate_docling_artifact_object_path(source_object_path: str) -> str:
        """Generate a deterministic object path for persisted Docling JSON artifacts."""
        source_name = Path(str(source_object_path or "")).name or "document"
        safe_name = MinIOService._sanitize_file_name(source_name)
        stem = Path(safe_name).stem or "document"
        path_hash = uuid.uuid5(uuid.NAMESPACE_URL, str(source_object_path or "")).hex[:12]
        return f"artifacts/{path_hash}_{stem}.docling.json"

    @staticmethod
    async def upload_preview_artifact(
        object_path: str,
        content: bytes,
        *,
        content_type: str = "text/html; charset=utf-8",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload a generated preview artifact to MinIO."""
        if not str(object_path or "").strip():
            raise ValueError("Preview artifact object path cannot be empty")
        payload = bytes(content or b"")
        if not payload:
            raise ValueError("Preview artifact content cannot be empty")

        stream = BytesIO(payload)
        normalized_metadata = cast(
            dict[str, str | list[str] | tuple[str]] | None,
            MinIOService._normalize_object_metadata(metadata),
        )
        await asyncio.to_thread(
            minio_client.put_object,
            bucket_name=settings.minio_bucket_name,
            object_name=object_path,
            data=stream,
            length=len(payload),
            content_type=content_type,
            metadata=normalized_metadata,
        )
        return object_path

    @staticmethod
    def infer_file_type_from_object_path(object_path: str) -> str | None:
        suffix = Path(str(object_path or "")).suffix.lower().lstrip(".")
        return suffix or None

    @staticmethod
    async def get_file_url(
        object_path: str,
        expires_in: int = 3600,
        *,
        file_type: str | None = None,
    ) -> str:
        """Generate a presigned download URL."""
        response_headers = MinIOService._build_response_headers(object_path, file_type=file_type)
        url = await asyncio.to_thread(
            minio_client.presigned_get_object,
            bucket_name=settings.minio_bucket_name,
            object_name=object_path,
            expires=timedelta(seconds=expires_in),
            response_headers=cast(dict[str, str | list[str] | tuple[str]] | None, response_headers or None),
        )
        return str(url)

    @staticmethod
    async def stat_object(object_path: str) -> Any:
        """Fetch object metadata asynchronously."""
        return await asyncio.to_thread(
            minio_client.stat_object,
            settings.minio_bucket_name,
            object_path,
        )

    @staticmethod
    async def delete_object(object_path: str) -> None:
        """Delete one object from the MinIO bucket."""
        if not str(object_path or "").strip():
            return
        await asyncio.to_thread(
            minio_client.remove_object,
            settings.minio_bucket_name,
            object_path,
        )

    @staticmethod
    def _sanitize_file_name(file_name: str, *, file_type: str = "") -> str:
        base_name = Path(str(file_name or "")).name.strip() or "document"
        base_name = re.sub(r'[\/:*?"<>|]+', "_", base_name)
        base_name = re.sub(r"\s+", " ", base_name).strip(" .") or "document"

        expected_suffix = f".{file_type.lower().lstrip('.')}" if file_type else ""
        current_suffix = Path(base_name).suffix.lower()
        if expected_suffix and current_suffix != expected_suffix:
            stem = Path(base_name).stem or base_name
            base_name = f"{stem}{expected_suffix}"

        return base_name

    @staticmethod
    def _build_response_headers(object_path: str, *, file_type: str | None = None) -> dict[str, str]:
        file_name = Path(str(object_path or "")).name or "document"
        quoted_file_name = file_name.replace('"', "")
        safe_file_name = quote(quoted_file_name)
        response_headers = {
            "response-content-disposition": (
                f'inline; filename="{quoted_file_name}"; filename*=UTF-8\'\'{safe_file_name}'
            )
        }

        content_type = file_type_to_content_type(file_type or "")
        if content_type:
            response_headers["response-content-type"] = content_type

        return response_headers

    @staticmethod
    def _normalize_object_metadata(metadata: dict[str, str] | None) -> dict[str, str] | None:
        if not metadata:
            return None
        normalized: dict[str, str] = {}
        for key, value in metadata.items():
            safe_key = str(key or "").strip()
            if not safe_key:
                continue
            safe_value = str(value or "")
            try:
                safe_value.encode("ascii")
            except UnicodeEncodeError:
                safe_value = quote(safe_value, safe="")
            normalized[safe_key] = safe_value
        return normalized or None
