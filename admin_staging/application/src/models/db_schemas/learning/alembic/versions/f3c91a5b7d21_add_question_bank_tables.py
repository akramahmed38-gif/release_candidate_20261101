"""Add question bank tables

Revision ID: f3c91a5b7d21
Revises: 84fdefb8f3eb
Create Date: 2026-07-12 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3c91a5b7d21"
down_revision: Union[str, Sequence[str], None] = "84fdefb8f3eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "question_bank_items",
        sa.Column("bank_question_id", sa.String(), nullable=False),
        sa.Column("question_text", sa.String(), nullable=False),
        sa.Column("question_type", sa.String(length=50), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("question_group", sa.String(), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_deleted", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("bank_question_id"),
    )
    op.create_index(
        op.f("ix_question_bank_items_bank_question_id"),
        "question_bank_items",
        ["bank_question_id"],
        unique=False,
    )

    op.create_table(
        "question_bank_choices",
        sa.Column("bank_choice_id", sa.String(), nullable=False),
        sa.Column("bank_question_id", sa.String(), nullable=False),
        sa.Column("choice_text", sa.String(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("choice_order", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["bank_question_id"],
            ["question_bank_items.bank_question_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("bank_choice_id"),
    )
    op.create_index(
        op.f("ix_question_bank_choices_bank_choice_id"),
        "question_bank_choices",
        ["bank_choice_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_question_bank_choices_bank_choice_id"), table_name="question_bank_choices")
    op.drop_table("question_bank_choices")
    op.drop_index(op.f("ix_question_bank_items_bank_question_id"), table_name="question_bank_items")
    op.drop_table("question_bank_items")
