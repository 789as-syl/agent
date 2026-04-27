"""核心基础设施模块：log_config。"""

import logging
import sys
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.config import settings


def setup_logging() -> None:
    """
    配置结构化日志，支持 request_id 上下文追踪。
    该函数应在应用启动时调用一次。
    """

    # 1. 将配置中的日志级别字符串（如 "INFO"）转换为 logging 模块的常量
    log_level = getattr(logging, settings.log_level.upper(), logging.DEBUG)

    # 2. 定义 structlog 的处理链（Processor Pipeline）
    #    每个 processor 按顺序处理日志事件，逐步丰富信息，最终渲染输出。
    processors: list[Any] = [
        # ① 合并通过 bind_contextvars 绑定的上下文变量（如 request_id）
        structlog.contextvars.merge_contextvars,

        # ② 根据日志方法自动添加 "level" 字段（如 "info", "error"）
        structlog.processors.add_log_level,

        # ③ 当调用 logger.exception() 时，自动渲染调用栈信息
        structlog.processors.StackInfoRenderer(),

        # ④ 确保异常信息（exc_info=True）被正确格式化
        structlog.dev.set_exc_info,

        # ⑤ 添加 ISO 8601 格式的时间戳字段 "timestamp"
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # 3. 根据配置选择最终渲染器（Renderer）
    if settings.log_format == "json":
        # 生产环境：输出纯 JSON，便于 Logstash/Fluentd 收集
        processors.append(structlog.processors.JSONRenderer())
    else:
        # 开发环境：输出彩色、对齐的控制台格式，人眼友好
        processors.append(structlog.dev.ConsoleRenderer())

    # 4. 应用 structlog 全局配置
    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),  # 直接打印到标准输出
        cache_logger_on_first_use=True,                 # 缓存 logger 实例，提高性能
    )

    # 5. 配置标准 logging 模块（作为 structlog 的底层输出管道）
    #    structlog 最终会调用 logging 模块来真正写入日志流。
    logging.basicConfig(
        format="%(message)s",   # 只输出消息体，因为 structlog 已经完成了格式化
        stream=sys.stdout,      # 输出到标准输出（容器/云原生环境最佳实践）
        level=log_level,
    )


def get_logger(name: str | None = None) -> Any:
    """
    获取一个结构化日志记录器实例。

    参数:
        name: 通常传入 `__name__`，用于标识日志来源模块。
    """
    return structlog.get_logger(name)


def set_request_id(request_id: str) -> None:
    """
    将 request_id 绑定到当前上下文中。
    后续所有通过 `get_logger()` 打印的日志都会自动包含此字段。

    典型调用场景：FastAPI 中间件，在请求到达时调用。
    """
    bind_contextvars(request_id=request_id)


def clear_request_id() -> None:
    """
    清空当前上下文绑定的所有变量。
    必须在请求结束时调用，避免上下文污染（例如线程池复用时的数据残留）。

    典型调用场景：FastAPI 中间件，在响应返回后调用。
    """
    clear_contextvars()
