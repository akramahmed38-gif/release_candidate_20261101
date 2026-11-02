"""add daily brief tables

Revision ID: b5d9e6a1c3f0
Revises: a91b3e4c7d22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5d9e6a1c3f0"
down_revision: Union[str, Sequence[str], None] = "a91b3e4c7d22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_briefs",
        sa.Column("brief_id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("brief_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("audience_type", sa.String(length=30), nullable=False, server_default="all_retail"),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("published_by", sa.String(length=255)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_daily_briefs_status", "daily_briefs", ["status"])
    op.create_index("ix_daily_briefs_brief_date", "daily_briefs", ["brief_date"])
    op.execute("CREATE UNIQUE INDEX uq_daily_briefs_one_live ON daily_briefs (status) WHERE status = 'LIVE'")
    op.create_table("daily_brief_blocks", sa.Column("block_id", sa.String(), primary_key=True), sa.Column("brief_id", sa.String(), sa.ForeignKey("daily_briefs.brief_id", ondelete="CASCADE"), nullable=False), sa.Column("block_type", sa.String(length=40), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("content_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("brief_id", "position", name="uq_daily_brief_block_position"))
    op.create_table("daily_brief_reads", sa.Column("read_id", sa.String(), primary_key=True), sa.Column("brief_id", sa.String(), sa.ForeignKey("daily_briefs.brief_id", ondelete="CASCADE"), nullable=False), sa.Column("user_email", sa.String(length=255), nullable=False), sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("brief_id", "user_email", name="uq_daily_brief_read_user"))
    op.create_table("daily_brief_views", sa.Column("view_id", sa.String(), primary_key=True), sa.Column("brief_id", sa.String(), sa.ForeignKey("daily_briefs.brief_id", ondelete="CASCADE"), nullable=False), sa.Column("user_email", sa.String(length=255), nullable=False), sa.Column("first_viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("last_viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("view_count", sa.Integer(), nullable=False, server_default="1"), sa.UniqueConstraint("brief_id", "user_email", name="uq_daily_brief_view_user"))


def downgrade() -> None:
    op.drop_table("daily_brief_views")
    op.drop_table("daily_brief_reads")
    op.drop_table("daily_brief_blocks")
    op.drop_index("uq_daily_briefs_one_live", table_name="daily_briefs")
    op.drop_table("daily_briefs")
