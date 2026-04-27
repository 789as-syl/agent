"""add retrieval log evidence sidecar columns

Revision ID: retrieval_evidence0423
Revises: drop_retrieval_rewrite_cols0421
Create Date: 2026-04-23 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "retrieval_evidence0423"
down_revision: str | None = "drop_retrieval_rewrite_cols0421"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "retrieval_logs",
        sa.Column(
            "anchor_kp_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            comment="evidence 口径: 锚点知识点 ID 列表 (可回退映射到 direct_hit_kp_ids)",
        ),
    )
    op.add_column(
        "retrieval_logs",
        sa.Column(
            "expanded_kp_ids_non_anchor",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            comment="evidence 口径: 扩展命中但非锚点的知识点 ID 列表 (可回退映射到 mapped_kp_ids)",
        ),
    )
    op.add_column(
        "retrieval_logs",
        sa.Column(
            "final_evidence_kp_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            comment="evidence 口径: 最终证据聚合后的知识点 ID 列表 (可回退映射到 final_kp_ids)",
        ),
    )


def downgrade() -> None:
    op.drop_column("retrieval_logs", "final_evidence_kp_ids")
    op.drop_column("retrieval_logs", "expanded_kp_ids_non_anchor")
    op.drop_column("retrieval_logs", "anchor_kp_ids")
