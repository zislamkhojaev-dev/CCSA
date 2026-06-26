"""research_studies table

Revision ID: 002
Revises: 001
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_studies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("filters_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("call_count", sa.Integer(), server_default="0"),
        sa.Column("call_ids", postgresql.JSONB(), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("report_markdown", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_research_studies_user_id", "research_studies", ["user_id"])
    op.create_index("ix_research_studies_status", "research_studies", ["status"])
    op.create_index("ix_research_studies_created_at", "research_studies", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_research_studies_created_at", table_name="research_studies")
    op.drop_index("ix_research_studies_status", table_name="research_studies")
    op.drop_index("ix_research_studies_user_id", table_name="research_studies")
    op.drop_table("research_studies")
