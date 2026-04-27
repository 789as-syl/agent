"""add admin user status snapshot fields

Revision ID: add_admin_user_status_snapshot
Revises: add_conversation_memories
Create Date: 2026-04-14 10:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_admin_user_status_snapshot"
down_revision: Union[str, None] = "add_conversation_memories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("status_changed_by_user_id", sa.UUID(), nullable=True))
    op.add_column("users", sa.Column("ban_reason", sa.Text(), nullable=True))
    op.create_index(
        "ix_users_status_changed_by_user_id",
        "users",
        ["status_changed_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_users_status_changed_by_user_id_users",
        "users",
        "users",
        ["status_changed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_status_changed_by_user_id_users", "users", type_="foreignkey")
    op.drop_index("ix_users_status_changed_by_user_id", table_name="users")
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "status_changed_by_user_id")
    op.drop_column("users", "status_changed_at")
