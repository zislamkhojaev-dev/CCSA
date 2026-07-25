"""analysis_results.topic column for call topic classification

Revision ID: 004
Revises: 003
Create Date: 2026-07-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_results", sa.Column("topic", sa.String(120), nullable=True))
    op.create_index("ix_analysis_results_topic", "analysis_results", ["topic"])


def downgrade() -> None:
    op.drop_index("ix_analysis_results_topic", table_name="analysis_results")
    op.drop_column("analysis_results", "topic")
