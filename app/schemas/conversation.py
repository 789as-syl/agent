"""Schema模块：conversation。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    """
    创建会话的请求体模型。

    客户端在创建新会话时，可指定标题（若不提供则使用默认值）。
    """

    title: str = Field(
        default="New Conversation",      # 默认标题
        min_length=1,                    # 最小长度 1 个字符
        max_length=255,                  # 最大长度 255 个字符（与数据库字段匹配）
        description="会话标题，默认为 'New Conversation'"
    )


class ConversationUpdateRequest(BaseModel):
    """
    更新会话标题的请求体模型。

    用于 PATCH /{conversation_id} 端点，允许部分更新会话属性。
    """

    title: str = Field(
        min_length=1,
        max_length=255,
        description="新的会话标题，长度 1-255 个字符"
    )


class ConversationResponse(BaseModel):
    """
    会话的响应模型，用于 API 返回单条会话数据。

    包含会话的所有公开字段，包括软删除标记（管理后台可能需要展示）。
    """

    id: UUID
    """会话唯一标识 UUID。"""

    user_id: UUID
    """所属用户的 UUID，用于多租户隔离。"""

    title: str
    """会话标题。"""

    is_deleted: bool
    """软删除标记。普通用户查询时通常不会返回已删除的会话，但管理接口可能需要此字段。"""

    created_at: datetime
    """会话创建时间（UTC），格式为 ISO 8601 字符串。"""

    updated_at: datetime
    """会话最后更新时间（UTC）。有新消息时会自动更新此字段。"""

    # Pydantic V2 配置：允许从 ORM 对象（如 SQLAlchemy 实例）自动映射字段
    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """
    分页查询会话列表的响应模型。
    """

    items: list[ConversationResponse]
    """当前页的会话列表。"""

    total: int
    """符合条件的会话总数，用于前端计算总页数。"""
