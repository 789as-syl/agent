
"""数据模型模块：base。"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    所有 SQLAlchemy ORM 模型的基类。

    继承自 DeclarativeBase 后，子类会自动获得声明式映射能力，
    无需再显式调用 declarative_base() 工厂函数。

    使用方式：
        class User(Base):
            __tablename__ = "users"
            id: Mapped[int] = mapped_column(primary_key=True)
            ...
    """

    pass


class TimestampMixin:
    """
    时间戳混入类，为模型添加 created_at 和 updated_at 字段。

    该 Mixin 不继承自任何基类，仅包含字段定义，可与 Base 的子类一起继承。
    字段说明：
        - created_at: 记录创建时间，插入时由数据库自动填充为当前时间。
        - updated_at: 记录最后更新时间，插入时同 created_at，更新时自动刷新为当前时间。

    注意：
        - 使用 DateTime(timezone=True) 确保时区感知，数据库存储带时区的 TIMESTAMP。
        - server_default=func.now() 由数据库服务器生成默认值，不受应用服务器时间影响。
        - onupdate=func.now() 在每次 UPDATE 时由数据库自动更新时间。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),        # 带时区的日期时间类型
        nullable=False,                 # 不允许为空
        server_default=func.now(),      # 数据库层面的默认值为当前时间戳（CURRENT_TIMESTAMP）
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),      # 插入时的默认值
        onupdate=func.now(),            # 更新记录时，由数据库自动设置为当前时间
    )
