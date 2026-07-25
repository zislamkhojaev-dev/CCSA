"""calls.updated_at so stuck processing states can be detected

Revision ID: 005
Revises: 004
Create Date: 2026-07-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.execute("UPDATE calls SET updated_at = created_at WHERE updated_at IS NULL")
    op.create_index("ix_calls_status_updated_at", "calls", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_calls_status_updated_at", table_name="calls")
    op.drop_column("calls", "updated_at")
