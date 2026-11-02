"""Add unique constraint for exam attempt numbering

Revision ID: a91b3e4c7d22
Revises: 4c2a6d7b9e10
Create Date: 2026-07-29 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a91b3e4c7d22"
down_revision: Union[str, Sequence[str], None] = "4c2a6d7b9e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("exam_attempts", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_exam_attempts_exam_employee_attempt_number",
            ["exam_id", "employee_id", "attempt_number"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("exam_attempts", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_exam_attempts_exam_employee_attempt_number",
            type_="unique",
        )
