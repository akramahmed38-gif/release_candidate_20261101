from sqlalchemy import Table, Column, String, ForeignKey
from .learning_base import SQLAlchemyBase

# Association table for Many-to-Many relationship between Exam and Material
exam_materials = Table(
    "exam_materials",
    SQLAlchemyBase.metadata,
    Column("exam_id", String, ForeignKey("exams.exam_id", ondelete="CASCADE"), primary_key=True),
    Column("material_idmaterial_id", String, ForeignKey("materials.material_id", ondelete="CASCADE"), primary_key=True),
)

# Association table for Many-to-Many relationship between Exam and Employee

exam_employees = Table(
    "exam_employees",
    SQLAlchemyBase.metadata,
    Column("exam_id", String, ForeignKey("exams.exam_id", ondelete="CASCADE"), primary_key=True),
    Column("employee_id", String, ForeignKey("employees.employee_id", ondelete="CASCADE"), primary_key=True),
)
