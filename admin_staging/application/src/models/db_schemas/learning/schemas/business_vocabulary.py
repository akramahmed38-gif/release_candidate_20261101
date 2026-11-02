import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from models.db_schemas.learning.schemas.learning_base import SQLAlchemyBase


class VocabularyCategory(SQLAlchemyBase):
    __tablename__ = "vocabulary_categories"

    category_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False, unique=True)
    arabic_name = Column(String(120), nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    items = relationship("VocabularyItem", back_populates="category", cascade="all, delete-orphan")


class VocabularyItem(SQLAlchemyBase):
    __tablename__ = "vocabulary_items"

    vocabulary_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    english_text = Column(String(180), nullable=False)
    arabic_text = Column(Text, nullable=False)
    # Optional override for acronyms such as POS and KYC; retail users still see english_text.
    speech_text = Column(String(180), nullable=True)
    category_id = Column(
        String(36),
        ForeignKey("vocabulary_categories.category_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    category = relationship("VocabularyCategory", back_populates="items")

    __table_args__ = (
        UniqueConstraint("category_id", "english_text", name="uq_vocabulary_item_category_english"),
        Index("ix_vocabulary_items_active_category_order", "is_active", "category_id", "display_order"),
    )
