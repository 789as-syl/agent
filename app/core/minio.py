"""核心基础设施模块：minio。"""

import asyncio

import urllib3
from minio import Minio

from app.core.config import settings

# ---------- 配置自定义 HTTP 客户端以支持连接池 ----------
_http_client = urllib3.PoolManager(
    maxsize=settings.minio_max_connections,
    cert_reqs="CERT_NONE" if not settings.minio_secure else "CERT_REQUIRED",
)

# ---------- 全局 MinIO 客户端实例 ----------
minio_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
    http_client=_http_client,
)


async def init_minio() -> None:
    """初始化 MinIO 客户端并确保默认存储桶已存在。

    使用 asyncio.to_thread 将同步调用移至线程池，
    避免阻塞 FastAPI 事件循环。
    """
    await asyncio.to_thread(_init_minio_sync)


def _init_minio_sync() -> None:
    """同步初始化：检查并创建存储桶。"""
    if not minio_client.bucket_exists(settings.minio_bucket_name):
        minio_client.make_bucket(settings.minio_bucket_name)


async def check_minio() -> bool:
    """检测 MinIO 服务连通性（异步版本）。

    使用 asyncio.to_thread 将同步 list_buckets 调用移至线程池。
    """
    try:
        await asyncio.to_thread(minio_client.list_buckets)
        return True
    except Exception:
        return False
