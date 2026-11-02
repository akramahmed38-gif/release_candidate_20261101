"""
materials Model
-----------
Represents a file uploaded as training material in the HR Training System.
each material has a unique ID, name, group, training type, and timestamps for creation and updates.
"""
import os
import uuid
from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from .learning_base import SQLAlchemyBase
from .association_table import exam_materials

class Material(SQLAlchemyBase):
    __tablename__ = "materials"

    material_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    material_name = Column(String, nullable=False)
    material_group = Column(String, nullable=False)
    material_training_type = Column(String, nullable=False)

    is_deleted = Column(Boolean, default=False) # Soft delete flag

    # Many-to-Many relationship to Exam
    exams = relationship(
        "Exam", 
        secondary=exam_materials,
        back_populates="materials",
        lazy="selectin"  # Use 'selectin' loading for better performance with many-to-many
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

def main():
    print(
        f"Welcome from `{os.path.basename(__file__)}`: Nothing to do ___^__^__ ..."
    )
if __name__ == "__main__":
    main()
# python -m src.models.db_schemas.hr.schemas.asset
