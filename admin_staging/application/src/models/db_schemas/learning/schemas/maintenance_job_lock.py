from sqlalchemy import Column, DateTime, String, Text

from .learning_base import SQLAlchemyBase


class MaintenanceJobLock(SQLAlchemyBase):
    __tablename__ = "maintenance_job_locks"

    job_name = Column(String, primary_key=True)
    locked_until = Column(DateTime(timezone=True), nullable=True, index=True)
    locked_by = Column(String, nullable=True)
    last_started_at = Column(DateTime(timezone=True), nullable=True)
    last_finished_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String, nullable=True)
    last_report = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
