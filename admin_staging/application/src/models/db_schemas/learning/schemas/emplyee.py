"""
employees Model
# HR_ID, Name, Title, Branch, Area,	Region,	Division (Fawry || Fawry Plus), Department (Retail), Sub Department(Mini, Flex, General, kiosik)
-------------
Represents an employee in the HR Training System.
each employee has a unique ID, name, email, branch, position, and timestamps for creation and updates.
## Relationships
- Many Employees → Many Exams: An employee can take multiple exams, and each exam can be taken by multiple employees.
"""

import os
import uuid
from sqlalchemy import Boolean, Column, ForeignKey, String, DateTime, func
from sqlalchemy.orm import relationship
from .learning_base import SQLAlchemyBase
from .association_table import exam_employees



class Employee(SQLAlchemyBase):
    __tablename__ = "employees"

    # hr_id, name, title, branch, area,	region,	division (Fawry || Fawry Plus), department (Retail, admin, hr), sub_department(Mini, Flex, General, kiosik), email, password

    employee_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    hr_id =  Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    title = Column(String, nullable=False)
    department = Column(String, nullable=False, default="Retail") # Retail, admin, hr || Act as Role

    email = Column(String, unique=True, nullable=False, index=True)     # Employee's email for login
    password = Column(String, nullable=False, default="change_me_123")  # default password to be changed on first login

    # Foreign Key to Branch
    branch_code = Column(String, ForeignKey("branches.branch_code"), nullable=False, index=True)
    employment_status = Column(String, nullable=False, default="active", server_default="active", index=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    resigned_at = Column(DateTime(timezone=True), nullable=True, index=True)
    resigned_reason = Column(String, nullable=True)
    resignation_type = Column(String, nullable=True)
    resigned_by = Column(String, nullable=True)
    reactivated_at = Column(DateTime(timezone=True), nullable=True)
    reactivated_by = Column(String, nullable=True)
    auto_resign_exempt = Column(Boolean, nullable=False, default=False, server_default="0")
    login_history_state = Column(String, nullable=False, default="pending_backfill", server_default="pending_backfill")

    # Many-to-Many relationship to Exam
    exams = relationship(
        "Exam",    # Class Name where the relation is defined with
        secondary=exam_employees, # association table
        back_populates="employees",  # in Exam, the attribute that points back to Employee
        lazy="selectin"  # Use 'selectin' loading for better performance with many-to-many
    )

    # Each employee belongs to one branch
    # Many-to-one relationship with Branch
    branch = relationship(
        "Branch",  # Class Name where the relation is defined with
        back_populates="employees",  # in Branch, the attribute that points back to Employee
        lazy="joined"  # Use 'joined' loading for one-to-one relationships
    )

    status_history = relationship(
        "EmploymentStatusHistory",
        back_populates="employee",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

def main():
    """Create all tables in the database."""
    print(
        f"Welcome from `{os.path.basename(__file__)}`: NOthing to do ___^__^__ ..."
    )

if __name__ == "__main__":
    main()
# python -m src.models.db_schemas.learning.schemas.emplyee

