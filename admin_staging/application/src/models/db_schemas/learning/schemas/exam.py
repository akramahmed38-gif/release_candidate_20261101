"""
exams Model
-------------
Represents an exam in the HR Training System.
each exam has a unique ID, title, description, status, duration, start and end dates, and timestamps for creation and updates.
## Relationships
- One Exam → Many Materials: An exam can be associated with multiple training materials.
"""

import os
import uuid
from sqlalchemy import Boolean, Column, Float, Integer, String, DateTime, func, Text
from sqlalchemy.orm import relationship
from .learning_base import SQLAlchemyBase
from .association_table import exam_materials, exam_employees

class Exam(SQLAlchemyBase):
    __tablename__ = "exams"

    exam_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    title = Column(String(255), nullable=False)
    description = Column(String, nullable=False)
    exam_status = Column(String(50), nullable=False, default="Open")  # e.g., Open, Closed, On Hold
    exam_level = Column(String(50), nullable=False, default="Entry Level")
    duration_minutes = Column(Integer, nullable=False)  # Duration of the exam in minutes
    passing_percent = Column(Float, nullable=True, default=60.0)
    number_of_attempts_allowed = Column(Integer, nullable=True, default=1)
    start_date = Column(DateTime(timezone=True), nullable=False) # When the exam starts
    end_date = Column(DateTime(timezone=True), nullable=False) # When the exam ends
    is_deleted = Column(Boolean, default=False) # Soft delete flag

    audience_mode = Column(String(20), nullable=False, default="all")
    audience_filters = Column(Text, nullable=True)
    audience_manual_hr_ids = Column(Text, nullable=True)

    # Many-to-Many relationship to Material
    materials = relationship(
        "Material",    # Class Name where the relation is defined with
        secondary=exam_materials, # association table
        back_populates="exams",  # in Material, the attribute that points back to Exam
        lazy="selectin"  # Use 'selectin' loading for better performance with many-to-many
    )

    # One-to-Many relationship to Question
    questions = relationship(
        "Question",
        back_populates="exam",
        lazy="selectin",
        cascade="all, delete-orphan"  # Automatically delete questions when exam is deleted
    )

    employees = relationship(
        "Employee",    # Class Name where the relation is defined with
        secondary=exam_employees, # association table
        back_populates="exams",  # in Employee, the attribute that points back to Exam
        lazy="selectin"  # Use 'selectin' loading for better performance with many-to-many
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
# python -m src.models.db_schemas.hr.schemas.project
