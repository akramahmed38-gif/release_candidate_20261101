"""Add resigned users lifecycle schema

Revision ID: 4c2a6d7b9e10
Revises: f3c91a5b7d21
Create Date: 2026-07-21 16:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4c2a6d7b9e10"
down_revision: Union[str, Sequence[str], None] = "f3c91a5b7d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("employment_status", sa.String(length=20), nullable=False, server_default="active")
        )
        batch_op.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("resigned_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("resigned_reason", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("resignation_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("resigned_by", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reactivated_by", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("auto_resign_exempt", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(
            sa.Column(
                "login_history_state",
                sa.String(length=50),
                nullable=False,
                server_default="pending_backfill",
            )
        )
        batch_op.create_index("ix_employees_employment_status", ["employment_status"], unique=False)
        batch_op.create_index("ix_employees_last_login_at", ["last_login_at"], unique=False)
        batch_op.create_index("ix_employees_resigned_at", ["resigned_at"], unique=False)
        batch_op.create_index("ix_employees_auto_resign_exempt", ["auto_resign_exempt"], unique=False)
        batch_op.create_index("ix_employees_login_history_state", ["login_history_state"], unique=False)

    op.create_table(
        "employment_status_history",
        sa.Column("history_id", sa.String(), nullable=False),
        sa.Column("employee_id", sa.String(), nullable=False),
        sa.Column("previous_status", sa.String(), nullable=True),
        sa.Column("new_status", sa.String(), nullable=False),
        sa.Column("change_type", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.employee_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("history_id"),
    )
    op.create_index(
        "ix_employment_status_history_employee_id",
        "employment_status_history",
        ["employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_employment_status_history_change_type",
        "employment_status_history",
        ["change_type"],
        unique=False,
    )
    op.create_index(
        "ix_employment_status_history_changed_at",
        "employment_status_history",
        ["changed_at"],
        unique=False,
    )

    op.create_table(
        "maintenance_job_locks",
        sa.Column("job_name", sa.String(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(), nullable=True),
        sa.Column("last_report", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_name"),
    )
    op.create_index(
        "ix_maintenance_job_locks_locked_until",
        "maintenance_job_locks",
        ["locked_until"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_maintenance_job_locks_locked_until", table_name="maintenance_job_locks")
    op.drop_table("maintenance_job_locks")

    op.drop_index("ix_employment_status_history_changed_at", table_name="employment_status_history")
    op.drop_index("ix_employment_status_history_change_type", table_name="employment_status_history")
    op.drop_index("ix_employment_status_history_employee_id", table_name="employment_status_history")
    op.drop_table("employment_status_history")

    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_index("ix_employees_login_history_state")
        batch_op.drop_index("ix_employees_auto_resign_exempt")
        batch_op.drop_index("ix_employees_resigned_at")
        batch_op.drop_index("ix_employees_last_login_at")
        batch_op.drop_index("ix_employees_employment_status")
        batch_op.drop_column("login_history_state")
        batch_op.drop_column("auto_resign_exempt")
        batch_op.drop_column("reactivated_by")
        batch_op.drop_column("reactivated_at")
        batch_op.drop_column("resigned_by")
        batch_op.drop_column("resignation_type")
        batch_op.drop_column("resigned_reason")
        batch_op.drop_column("resigned_at")
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("employment_status")
