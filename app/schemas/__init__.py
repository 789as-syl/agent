"""后端包初始化模块：app.schemas。"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """
    存活探针（Liveness Probe）的响应模型。

    用于简单判断服务进程是否正在运行且能够处理请求。
    通常对应 Kubernetes 的 livenessProbe，若失败则容器会被重启。
    """

    status: str       # 服务状态，通常固定返回 "ok" 或 "healthy"
    service: str      # 服务名称，便于在日志和监控中区分不同服务


class ReadinessCheck(BaseModel):
    """
    单个依赖服务的就绪检查结果模型。

    用于详细描述某个外部依赖（如数据库、Redis、MinIO）的连接状态。
    """

    service: str           # 被检查的服务名称（如 "postgresql", "redis"）
    status: str            # 状态：通常为 "ok" 或 "error"
    message: str | None = None  # 附加信息，当检查失败时用于说明原因


class ReadinessResponse(BaseModel):
    """
    就绪探针（Readiness Probe）的响应模型。

    用于判断服务是否已准备好接收流量。它会汇总所有关键依赖的检查结果。
    通常对应 Kubernetes 的 readinessProbe，若失败则服务会被从负载均衡中摘除。
    """

    status: str                   # 整体就绪状态，例如 "ready" 或 "not_ready"
    checks: list[ReadinessCheck]  # 各项依赖检查的详细列表
