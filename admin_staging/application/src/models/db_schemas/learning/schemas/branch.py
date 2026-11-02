import os
import uuid
from sqlalchemy import Boolean, Column, Float, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from .learning_base import SQLAlchemyBase
from .association_table import exam_employees



class Branch(SQLAlchemyBase):
    __tablename__ = "branches"

    branch_code = Column(String, primary_key=True, index=True)
    branch_name = Column(String, unique=True, nullable=False)
    branch_region = Column(String, nullable=False)
    branch_area = Column(String, nullable=False)
    branch_division = Column(String, nullable=False)  # Fawry || Fawry Plus
    branch_sub_department = Column(String, nullable=False)  # Mini, Flex, General, kiosik


    # One-to-Many relationship to Employee
    # Each branch can have multiple employees
    employees = relationship(
        "Employee",  # Class Name where the relation is defined with
        back_populates="branch",  # in Employee, the attribute that points back to Branch
        lazy="selectin"  # Use 'selectin' loading for better performance with one-to-many
    )

