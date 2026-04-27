"""add chat run lineage

Revision ID: add_chat_run_lineage
Revises: vecfreshhnsw0415
Create Date: 2026-04-16 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_chat_run_lineage"
down_revision: str | None = "vecfreshhnsw0415"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_runs",
        sa.Column(
            "parent_run_id",
            sa.UUID(),
            nullable=True,
            comment="父运行 ID; 子运行由哪个 run 派生而来",
        ),
    )
    op.add_column(
        "chat_runs",
        sa.Column(
            "retry_of_run_id",
            sa.UUID(),
            nullable=True,
            comment="若本次运行是 retry 产生, 则记录被重试的 run ID",
        ),
    )
    op.add_column(
        "chat_runs",
        sa.Column(
            "branch_key",
            sa.String(length=64),
            nullable=True,
            comment="逻辑分支键; retry 继承同一 branch_key, 后续 regenerate 可分叉新 branch",
        ),
    )

    op.create_foreign_key(
        "fk_chat_runs_parent_run_id_chat_runs",
        "chat_runs",
        "chat_runs",
        ["parent_run_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_chat_runs_retry_of_run_id_chat_runs",
        "chat_runs",
        "chat_runs",
        ["retry_of_run_id"],
        ["id"],
    )

    op.create_index("ix_chat_runs_parent_run_id", "chat_runs", ["parent_run_id"], unique=False)
    op.create_index("ix_chat_runs_retry_of_run_id", "chat_runs", ["retry_of_run_id"], unique=False)
    op.create_index("ix_chat_runs_branch_key", "chat_runs", ["branch_key"], unique=False)

    op.execute("UPDATE chat_runs SET branch_key = id::text WHERE branch_key IS NULL")


def downgrade() -> None:
    op.drop_index("ix_chat_runs_branch_key", table_name="chat_runs")
    op.drop_index("ix_chat_runs_retry_of_run_id", table_name="chat_runs")
    op.drop_index("ix_chat_runs_parent_run_id", table_name="chat_runs")

    op.drop_constraint("fk_chat_runs_retry_of_run_id_chat_runs", "chat_runs", type_="foreignkey")
    op.drop_constraint("fk_chat_runs_parent_run_id_chat_runs", "chat_runs", type_="foreignkey")

    op.drop_column("chat_runs", "branch_key")
    op.drop_column("chat_runs", "retry_of_run_id")
    op.drop_column("chat_runs", "parent_run_id")
