"""数据模型模块：enums。"""

from enum import Enum


class RunStatus(str, Enum):
    """Agent 运行状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class JobStatus(str, Enum):
    """任务状态枚举（入库任务、向量化任务共用）。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
