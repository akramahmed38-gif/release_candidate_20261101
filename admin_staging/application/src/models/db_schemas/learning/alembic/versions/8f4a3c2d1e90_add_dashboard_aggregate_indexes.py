"""add dashboard aggregate indexes

Revision ID: 8f4a3c2d1e90
Revises: b5d9e6a1c3f0
"""

from typing import Sequence, Union

from alembic import op


revision: str = "8f4a3c2d1e90"
down_revision: Union[str, Sequence[str], None] = "b5d9e6a1c3f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Covers dashboard employee scoping by role/status and the branch join.
    op.create_index(
        "ix_employees_dashboard_department_status_branch",
        "employees",
        ["department", "employment_status", "branch_code"],
    )
    # Supports scoped attempts by employee and reporting period.
    op.create_index(
        "ix_exam_attempts_dashboard_employee_submitted",
        "exam_attempts",
        ["employee_id", "submitted_at"],
    )
    # Supports the assignment-to-attempt join used by all exam aggregates.
    op.create_index(
        "ix_exam_attempts_dashboard_exam_employee_submitted",
        "exam_attempts",
        ["exam_id", "employee_id", "submitted_at"],
    )
    # Supports answer-level analysis when the detailed topic section is requested.
    op.create_index(
        "ix_exam_answers_dashboard_attempt_question",
        "exam_answers",
        ["attempt_id", "question_id"],
    )
    # Supports branch geography filters before the employee join.
    op.create_index(
        "ix_branches_dashboard_region_area_code",
        "branches",
        ["branch_region", "branch_area", "branch_code"],
    )
    # Supports active and overdue exam window aggregation.
    op.create_index(
        "ix_exams_dashboard_status_window",
        "exams",
        ["is_deleted", "exam_status", "start_date", "end_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_exams_dashboard_status_window", table_name="exams")
    op.drop_index("ix_branches_dashboard_region_area_code", table_name="branches")
    op.drop_index("ix_exam_answers_dashboard_attempt_question", table_name="exam_answers")
    op.drop_index("ix_exam_attempts_dashboard_exam_employee_submitted", table_name="exam_attempts")
    op.drop_index("ix_exam_attempts_dashboard_employee_submitted", table_name="exam_attempts")
    op.drop_index("ix_employees_dashboard_department_status_branch", table_name="employees")
