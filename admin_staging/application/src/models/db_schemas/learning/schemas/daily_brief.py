import uuid

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import relationship

from .learning_base import SQLAlchemyBase


class DailyBriefAction(SQLAlchemyBase):
    __tablename__ = "daily_brief_actions"
    action_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    brief_id = Column(String, nullable=False, index=True)
    action = Column(String(40), nullable=False)
    actor = Column(String(255), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)


class DailyBriefAudience(SQLAlchemyBase):
    __tablename__ = "daily_brief_audience"
    audience_id = Column(Integer, primary_key=True)
    recipients_json = Column(Text, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    updated_by = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DailyBrief(SQLAlchemyBase):
    __tablename__ = "daily_briefs"

    brief_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False)
    brief_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    audience_type = Column(String(30), nullable=False, default="all_retail")
    created_by = Column(String(255), nullable=False)
    published_by = Column(String(255), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    blocks = relationship("DailyBriefBlock", back_populates="brief", cascade="all, delete-orphan", order_by="DailyBriefBlock.position")
    reads = relationship("DailyBriefRead", back_populates="brief", cascade="all, delete-orphan")
    views = relationship("DailyBriefView", back_populates="brief", cascade="all, delete-orphan")
    feedback = relationship("DailyBriefFeedback", back_populates="brief", cascade="all, delete-orphan")
    email_batches = relationship("DailyBriefEmailBatch", back_populates="brief", cascade="all, delete-orphan")


# Enforces the one-live-brief rule at the SQLite database level.
Index("uq_daily_briefs_one_live", DailyBrief.status, unique=True, sqlite_where=text("status = 'LIVE'"))


class DailyBriefBlock(SQLAlchemyBase):
    __tablename__ = "daily_brief_blocks"

    block_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    brief_id = Column(String, ForeignKey("daily_briefs.brief_id", ondelete="CASCADE"), nullable=False, index=True)
    block_type = Column(String(40), nullable=False)
    position = Column(Integer, nullable=False)
    content_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    brief = relationship("DailyBrief", back_populates="blocks")

    __table_args__ = (UniqueConstraint("brief_id", "position", name="uq_daily_brief_block_position"),)


class DailyBriefRead(SQLAlchemyBase):
    __tablename__ = "daily_brief_reads"

    read_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    brief_id = Column(String, ForeignKey("daily_briefs.brief_id", ondelete="CASCADE"), nullable=False, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    brief = relationship("DailyBrief", back_populates="reads")

    __table_args__ = (UniqueConstraint("brief_id", "user_email", name="uq_daily_brief_read_user"),)


class DailyBriefView(SQLAlchemyBase):
    __tablename__ = "daily_brief_views"

    view_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    brief_id = Column(String, ForeignKey("daily_briefs.brief_id", ondelete="CASCADE"), nullable=False, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    first_viewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_viewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    view_count = Column(Integer, nullable=False, default=1)

    brief = relationship("DailyBrief", back_populates="views")

    __table_args__ = (UniqueConstraint("brief_id", "user_email", name="uq_daily_brief_view_user"),)


class DailyBriefFeedback(SQLAlchemyBase):
    __tablename__ = "daily_brief_feedback"

    feedback_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    brief_id = Column(String, ForeignKey("daily_briefs.brief_id", ondelete="CASCADE"), nullable=False, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    reaction = Column(String(10), nullable=True)
    comment = Column(Text, nullable=True)
    feedback_updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    brief = relationship("DailyBrief", back_populates="feedback")

    __table_args__ = (
        UniqueConstraint("brief_id", "user_email", name="uq_daily_brief_feedback_user"),
        CheckConstraint("reaction IS NULL OR reaction IN ('LIKE', 'UNLIKE')", name="ck_daily_brief_feedback_reaction"),
    )


class DailyBriefEmailBatch(SQLAlchemyBase):
    __tablename__ = "daily_brief_email_batches"

    batch_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    brief_id = Column(String, ForeignKey("daily_briefs.brief_id", ondelete="CASCADE"), nullable=False, index=True)
    triggered_by = Column(String(255), nullable=False, index=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    recipient_count = Column(Integer, nullable=False, default=0)
    accepted_count = Column(Integer, nullable=False, default=0)
    rejected_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="PENDING", index=True)

    brief = relationship("DailyBrief", back_populates="email_batches")
    recipients = relationship("DailyBriefEmailRecipient", back_populates="batch", cascade="all, delete-orphan", order_by="DailyBriefEmailRecipient.position")


class DailyBriefEmailRecipient(SQLAlchemyBase):
    __tablename__ = "daily_brief_email_recipients"

    recipient_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String, ForeignKey("daily_brief_email_batches.batch_id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_name = Column(String(255), nullable=False)
    recipient_email = Column(String(255), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    smtp_code = Column(Integer, nullable=True)
    smtp_message = Column(String(500), nullable=True)
    attempted_at = Column(DateTime(timezone=True), nullable=True)

    batch = relationship("DailyBriefEmailBatch", back_populates="recipients")

    __table_args__ = (UniqueConstraint("batch_id", "recipient_email", name="uq_daily_brief_email_batch_recipient"),)
