"""
OTP request model for login verification.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, func, Index
from .learning_base import SQLAlchemyBase


class OTPRequest(SQLAlchemyBase):
    __tablename__ = "otp_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, index=True)
    otp_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_otp_requests_email_used", "email", "is_used"),
    )
