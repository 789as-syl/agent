"""add knowledge point document metadata

Revision ID: add_kp_document_metadata0423
Revises: retrieval_evidence0423
Create Date: 2026-04-23 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "add_kp_document_metadata0423"
down_revision: str | None = "retrieval_evidence0423"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_points",
        sa.Column(
            "document_metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="文档级解析/缓存/质量元数据",
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_points", "document_metadata_json")
