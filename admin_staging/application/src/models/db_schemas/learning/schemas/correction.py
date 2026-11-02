from sqlalchemy import (
    Boolean, Column, Integer, String, DateTime, ForeignKey, Float, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .learning_base import SQLAlchemyBase
import uuid

class ExamAttempt(SQLAlchemyBase):
    __tablename__ = "exam_attempts"
    __table_args__ = (
        UniqueConstraint(
            "exam_id",
            "employee_id",
            "attempt_number",
            name="uq_exam_attempts_exam_employee_attempt_number",
        ),
    )

    attempt_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    exam_id = Column(String, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(String, ForeignKey("employees.employee_id", ondelete="CASCADE"), nullable=False)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # time when attempt started || When User clicks "Start Exam"
    submitted_at = Column(DateTime(timezone=True), nullable=True)                           # time when attempt was submitted || When User clicks "Submit Exam"


    total_score = Column(Float, nullable=True)       # computed after correction || 
    max_score = Column(Float, nullable=True)         # sum of question points    || 
    passed = Column(Boolean, default=False)          # pass/fail flag
    
    
    attempt_number = Column(Integer, nullable=False, default=1)
    
    exam = relationship("Exam") # Many-to-One
    employee = relationship("Employee") # Many-to-One
    answers = relationship( # One-to-Many
        "ExamAnswer",
        back_populates="attempt",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class ExamAnswer(SQLAlchemyBase):
    __tablename__ = "exam_answers"

    answer_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    attempt_id = Column(String, ForeignKey("exam_attempts.attempt_id", ondelete="CASCADE"), nullable=False)
    question_id = Column(String, ForeignKey("questions.question_id", ondelete="CASCADE"), nullable=False)

    # For MCQ/TF: store chosen option
    chosen_choice_id = Column(String, ForeignKey("question_choices.choice_id"), nullable=True)
    chosen_choice_ids = Column(String, nullable=True)

    # Scoring info
    is_correct = Column(Boolean, nullable=True)      # null before correction
    score_obtained = Column(Float, nullable=True)    # e.g. 0 to question.points

    attempt = relationship("ExamAttempt", back_populates="answers") # Many-to-One
    question = relationship("Question") # Many-to-One
    chosen_choice = relationship("QuestionChoice") # Many-to-One




# 1) When user clicks “Start exam”
# ===================***********************========================
# def start_exam(db: Session, exam_id: str, employee_id: str):
#     attempt = ExamAttempt(
#         exam_id=exam_id,
#         employee_id=employee_id,
#         # do NOT set started_at manually, DB will set it via server_default
#     )
#     db.add(attempt)
#     db.commit()
#     db.refresh(attempt)  # now attempt.started_at has the DB timestamp
#     return attempt

# ==================***********************==================
# ==================***********************==================
# ==================***********************==================

# 2) While user answers questions
# For each question answered you create or update ExamAnswer rows referencing this attempt_id:

# def save_answer(db: Session, attempt_id: str, question_id: str, choice_id: str | None, text_answer: str | None):
#     answer = ExamAnswer(
#         attempt_id=attempt_id,
#         question_id=question_id,
#         chosen_choice_id=choice_id,
#         text_answer=text_answer,
#     )
#     db.add(answer)
#     db.commit()
# All answers for this attempt are linked to one ExamAttempt via attempt_id.



# 3) When user clicks “Submit exam”
# You correct and close the attempt:

# from sqlalchemy import func as sa_func
# from datetime import datetime, timezone
# def submit_exam(db: Session, attempt_id: str, passing_percent: float = 60.0):
#     attempt = db.query(ExamAttempt).filter(ExamAttempt.attempt_id == attempt_id).one()

#     # 1) Auto-correct objective questions and compute total
#     total_score = 0.0
#     max_score = 0.0

#     for answer in attempt.answers:
#         q = answer.question  # via relationship
#         max_score += q.points

#         # example for MCQ/TF:
#         correct_choice = next((c for c in q.choices if c.is_correct), None)
#         if correct_choice and answer.chosen_choice_id == correct_choice.choice_id:
#             answer.is_correct = True
#             answer.score_obtained = q.points
#         else:
#             answer.is_correct = False
#             answer.score_obtained = 0
#         total_score += answer.score_obtained

#     # 2) Finalize attempt
#     attempt.total_score = total_score
#     attempt.max_score = max_score
#     attempt.passed = (total_score >= (passing_percent / 100.0) * max_score)
#     attempt.submitted_at = datetime.now(timezone.utc)

#     db.commit()

# duration = submitted_at - started_at.
# ​You can enforce time limits: if current time > started_at + duration_minutes, auto-submit or block.





