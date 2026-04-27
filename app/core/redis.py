"""核心基础设施模块：redis。"""

from __future__ import annotations

from uuid import UUID

import redis.asyncio as aioredis

from app.core.config import settings

# ---------- 全局异步 Redis 客户端实例 ----------
# 使用 aioredis.from_url 从配置的 URL 创建连接池客户端。
# 该客户端是异步安全的，所有操作都需要 await。
redis_client: aioredis.Redis = aioredis.from_url(
    settings.redis_url,            # Redis 连接 URL，例如 "redis://localhost:6379/0"
    encoding="utf-8",              # 读写字符串时的编码格式
    decode_responses=True,         # 自动将字节响应解码为字符串（省去手动 decode）
    health_check_interval=30,      # 每 30 秒检查一次连接健康状态，自动重连坏掉的连接
)

CHAT_RUN_INTERRUPT_SIGNAL_TTL_SECONDS = 60


def build_chat_run_interrupt_channel(run_id: UUID | str) -> str:
    return f"chat_run_interrupt:{run_id}"


def build_chat_run_interrupt_flag_key(run_id: UUID | str) -> str:
    return f"chat_run_interrupt_flag:{run_id}"


async def init_redis() -> None:
    """
    初始化 Redis 连接并验证连通性。
    应在 FastAPI 启动事件中调用，确保应用启动时 Redis 已就绪。
    """
    # ping() 会发送一个 PING 命令，若 Redis 正常则返回 True，否则抛出异常
    await redis_client.ping()


async def close_redis() -> None:
    """
    关闭 Redis 连接池。
    应在 FastAPI 关闭事件中调用，优雅释放连接资源。
    """
    await redis_client.close()
