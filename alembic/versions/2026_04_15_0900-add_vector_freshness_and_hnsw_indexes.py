"""add vector freshness metadata and hnsw indexes

Revision ID: vecfreshhnsw0415
Revises: add_admin_user_status_snapshot
Create Date: 2026-04-15 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "vecfreshhnsw0415"
down_revision: str | None = "add_admin_user_status_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "questions",
        sa.Column(
            "embedding_text_hash",
            sa.String(length=64),
            nullable=True,
            comment="当前题干向量对应的题干哈希, 用于判定向量是否过期",
        ),
    )
    op.add_column(
        "questions",
        sa.Column(
            "vectorized_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次成功生成题干向量的时间",
        ),
    )
    op.create_index("ix_questions_is_dirty", "questions", ["is_dirty"], unique=False)

    op.execute(
        """
        UPDATE questions
        SET is_dirty = TRUE,
            updated_at = NOW()
        WHERE question_embedding IS NOT NULL
          AND embedding_text_hash IS NULL
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_questions_question_embedding_hnsw
        ON questions
        USING hnsw (question_embedding vector_cosine_ops)
        WHERE question_embedding IS NOT NULL
          AND is_dirty = FALSE
          AND embedding_text_hash IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_point_chunks_embedding_hnsw
        ON knowledge_point_chunks
        USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_point_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_questions_question_embedding_hnsw")
    op.drop_index("ix_questions_is_dirty", table_name="questions")
    op.drop_column("questions", "vectorized_at")
    op.drop_column("questions", "embedding_text_hash")
