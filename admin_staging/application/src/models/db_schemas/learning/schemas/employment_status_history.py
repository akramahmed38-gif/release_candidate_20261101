import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import relationship

from .learning_base import SQLAlchemyBase


class EmploymentStatusHistory(SQLAlchemyBase):
    __tablename__ = "employment_status_history"

    history_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    employee_id = Column(String, ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False, index=True)
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    change_type = Column(String, nullable=False, index=True)
    reason = Column(String, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    changed_by = Column(String, nullable=True)
    metadata_json = Column("metadata", Text, nullable=True)

    employee = relationship("Employee", back_populates="status_history")
