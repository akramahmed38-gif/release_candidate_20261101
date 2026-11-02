import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from .learning_base import SQLAlchemyBase


class QuestionBankGroup(SQLAlchemyBase):
    __tablename__ = "question_bank_groups"

    group_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120, collation="NOCASE"), nullable=False, unique=True)
    description = Column(String(500), nullable=False, default="")
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    members = relationship("QuestionBankGroupMember", back_populates="group")


class QuestionBankGroupMember(SQLAlchemyBase):
    __tablename__ = "question_bank_group_members"
    __table_args__ = (UniqueConstraint("bank_question_id", name="uq_question_bank_group_member_item"),)

    bank_question_id = Column(String, ForeignKey("question_bank_items.bank_question_id", ondelete="CASCADE"), primary_key=True)
    group_id = Column(String, ForeignKey("question_bank_groups.group_id", ondelete="RESTRICT"), nullable=False, index=True)
    group = relationship("QuestionBankGroup", back_populates="members")
