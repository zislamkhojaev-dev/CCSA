"""tags reference table and call_tags.tag_id

Revision ID: 003
Revises: 002
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_tag_name"),
    )

    op.execute(
        """
        INSERT INTO tags (name)
        SELECT DISTINCT trim(tag)
        FROM call_tags
        WHERE tag IS NOT NULL AND trim(tag) != ''
        ON CONFLICT (name) DO NOTHING
        """
    )

    for default_name in ("жалоба", "продажа", "лояльный"):
        op.execute(
            sa.text("INSERT INTO tags (name) VALUES (:name) ON CONFLICT (name) DO NOTHING").bindparams(
                name=default_name
            )
        )

    op.add_column("call_tags", sa.Column("tag_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE call_tags ct
        SET tag_id = t.id
        FROM tags t
        WHERE trim(ct.tag) = t.name
        """
    )
    op.execute("DELETE FROM call_tags WHERE tag_id IS NULL")
    op.drop_constraint("uq_call_tag", "call_tags", type_="unique")
    op.drop_column("call_tags", "tag")
    op.alter_column("call_tags", "tag_id", nullable=False)
    op.create_foreign_key("fk_call_tags_tag_id", "call_tags", "tags", ["tag_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_call_tag", "call_tags", ["call_id", "tag_id"])


def downgrade() -> None:
    op.add_column("call_tags", sa.Column("tag", sa.String(100), nullable=True))
    op.execute(
        """
        UPDATE call_tags ct
        SET tag = t.name
        FROM tags t
        WHERE ct.tag_id = t.id
        """
    )
    op.alter_column("call_tags", "tag", nullable=False)
    op.drop_constraint("uq_call_tag", "call_tags", type_="unique")
    op.drop_constraint("fk_call_tags_tag_id", "call_tags", type_="foreignkey")
    op.drop_column("call_tags", "tag_id")
    op.create_unique_constraint("uq_call_tag", "call_tags", ["call_id", "tag"])
    op.drop_table("tags")
