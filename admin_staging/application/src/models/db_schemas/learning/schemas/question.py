import os
import uuid
from sqlalchemy import Boolean, Column, Integer, String, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from .learning_base import SQLAlchemyBase


class Question(SQLAlchemyBase):
    __tablename__ = "questions"
    
    question_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    exam_id = Column(String, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=False)

    question_text = Column(String, nullable=False)
    question_type = Column(String(50), nullable=False)  # MCQ, TF, Essay
    points = Column(Integer, nullable=False, default=1)

    question_group = Column(String, nullable=True)  # e.g., Technical, HR, Safety
    
    is_deleted = Column(Boolean, default=False)
    
    # Many-to-One relationship back to Exam
    exam = relationship("Exam", back_populates="questions")

    # One-to-Many relationship to QuestionChoice
    choices = relationship(
        "QuestionChoice", 
        back_populates="question",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)



class QuestionChoice(SQLAlchemyBase):
    __tablename__ = "question_choices"
    
    choice_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    question_id = Column(String, ForeignKey("questions.question_id", ondelete="CASCADE"), nullable=False)

    choice_text = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)  # Mark the correct answer
    choice_order = Column(Integer, nullable=True)  # To maintain choice order (A, B, C, D)
    
    is_deleted = Column(Boolean, default=False)
    
    # Many-to-One relationship back to Question
    question = relationship("Question", back_populates="choices")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class QuestionBankItem(SQLAlchemyBase):
    __tablename__ = "question_bank_items"

    bank_question_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    question_text = Column(String, nullable=False)
    question_type = Column(String(50), nullable=False)  # MCQ, TF, Essay
    points = Column(Integer, nullable=False, default=1)
    question_group = Column(String, nullable=True)
    is_favorite = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, default=False)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)

    choices = relationship(
        "QuestionBankChoice",
        back_populates="question",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class QuestionBankChoice(SQLAlchemyBase):
    __tablename__ = "question_bank_choices"

    bank_choice_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    bank_question_id = Column(
        String,
        ForeignKey("question_bank_items.bank_question_id", ondelete="CASCADE"),
        nullable=False,
    )
    choice_text = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)
    choice_order = Column(Integer, nullable=True)
    is_deleted = Column(Boolean, default=False)

    question = relationship("QuestionBankItem", back_populates="choices")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

