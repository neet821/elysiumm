"""Catalog database models."""

from .base import (
    Base,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    datetime,
    relationship,
)


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (UniqueConstraint("slug", name="uq_book_slug"),)

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(120), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    author = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    cover_url = Column(String(500), nullable=True)
    category = Column(String(80), nullable=True, index=True)
    tags_json = Column(Text, default="[]", nullable=False)
    reading_status = Column(String(30), default="unread", nullable=False, index=True)
    source = Column(String(40), default="manual", nullable=False, index=True)
    source_id = Column(String(255), nullable=True, index=True)
    isbn = Column(String(32), nullable=True, index=True)
    publication_year = Column(Integer, nullable=True)
    personal_rating = Column(Float, nullable=True)
    personal_notes = Column(Text, nullable=True)
    metadata_overrides_json = Column(Text, default="[]", nullable=False)
    reader_path = Column(String(1000), nullable=True)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    is_featured = Column(Boolean, default=False, nullable=False, index=True)
    display_order = Column(Integer, default=0, nullable=False)
    last_read_at = Column(DateTime, nullable=True)
    revision = Column(Integer, default=1, nullable=False)
    updated_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    updater = relationship("User")


class MediaEntry(Base):
    __tablename__ = "media_entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('movie', 'album', 'game')", name="ck_media_entries_kind"
        ),
        CheckConstraint(
            "personal_rating IS NULL OR (personal_rating >= 0 AND personal_rating <= 10)",
            name="ck_media_entries_personal_rating",
        ),
        UniqueConstraint(
            "kind",
            "source",
            "source_id",
            name="uq_media_entries_source_identity",
        ),
        Index("ix_media_entries_kind_activity", "kind", "activity_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(20), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    creator = Column(String(255), nullable=True)
    cover_url = Column(String(700), nullable=True)
    release_year = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    tags_json = Column(Text, default="[]", nullable=False)
    status = Column(String(30), default="planned", nullable=False, index=True)
    activity_at = Column(DateTime, nullable=True, index=True)
    personal_rating = Column(Float, nullable=True)
    personal_notes = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    is_featured = Column(Boolean, default=False, nullable=False, index=True)
    source = Column(String(40), default="manual", nullable=False, index=True)
    source_id = Column(String(255), nullable=True, index=True)
    external_url = Column(String(1000), nullable=True)
    metadata_json = Column(Text, default="{}", nullable=False)
    raw_metadata_json = Column(Text, default="{}", nullable=False)
    metadata_overrides_json = Column(Text, default="[]", nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    updated_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    updater = relationship("User")


class BookList(Base):
    __tablename__ = "book_lists"
    __table_args__ = (UniqueConstraint("slug", name="uq_book_list_slug"),)

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(120), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    display_order = Column(Integer, default=0, nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    updated_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    updater = relationship("User")
    items = relationship(
        "BookListItem",
        back_populates="book_list",
        cascade="all, delete-orphan",
        order_by="BookListItem.position",
    )


class BookListItem(Base):
    __tablename__ = "book_list_items"
    __table_args__ = (
        UniqueConstraint("list_id", "book_id", name="uq_book_list_item_book"),
        UniqueConstraint("list_id", "position", name="uq_book_list_item_position"),
        CheckConstraint("position >= 0", name="ck_book_list_item_position"),
    )

    id = Column(Integer, primary_key=True, index=True)
    list_id = Column(
        Integer,
        ForeignKey("book_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    book_list = relationship("BookList", back_populates="items")
    book = relationship("Book")
