"""Bookmarks database models."""

from .base import (
    Base,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    datetime,
    relationship,
)


class BookmarkFolder(Base):
    __tablename__ = "bookmark_folders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("bookmark_folders.id"), nullable=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(50), nullable=True)
    color = Column(String(20), nullable=True)
    sort_order = Column(Integer, default=0)
    is_sensitive = Column(Boolean, default=False, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    parent = relationship("BookmarkFolder", remote_side=[id])
    bookmarks = relationship("Bookmark", back_populates="folder")


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        Index("ix_bookmarks_public_created", "is_public", "created_at"),
        Index("ix_bookmarks_user_active", "user_id", "is_archived"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    folder_id = Column(Integer, ForeignKey("bookmark_folders.id"), nullable=True)
    title = Column(String(200), nullable=False)
    url = Column(String(1000), nullable=False)
    description = Column(Text, nullable=True)
    favicon = Column(String(500), nullable=True)
    preview_url = Column(String(1000), nullable=True)
    sort_order = Column(Integer, default=0)
    is_archived = Column(Boolean, default=False, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    visit_count = Column(Integer, default=0, nullable=False)
    show_description = Column(Boolean, default=True, nullable=False)
    show_preview = Column(Boolean, default=True, nullable=False)
    show_visit_count = Column(Boolean, default=False, nullable=False)
    allow_indexing = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_visited_at = Column(DateTime, nullable=True)

    user = relationship("User")
    folder = relationship("BookmarkFolder", back_populates="bookmarks")
    tag_relations = relationship(
        "BookmarkTagRelation", back_populates="bookmark", cascade="all, delete-orphan"
    )


class BookmarkTag(Base):
    __tablename__ = "bookmark_tags"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    bookmark_relations = relationship(
        "BookmarkTagRelation", back_populates="tag", cascade="all, delete-orphan"
    )


class BookmarkTagRelation(Base):
    __tablename__ = "bookmark_tag_relations"

    id = Column(Integer, primary_key=True, index=True)
    bookmark_id = Column(Integer, ForeignKey("bookmarks.id"), nullable=False)
    tag_id = Column(Integer, ForeignKey("bookmark_tags.id"), nullable=False)

    bookmark = relationship("Bookmark", back_populates="tag_relations")
    tag = relationship("BookmarkTag", back_populates="bookmark_relations")


class BookmarkImportJob(Base):
    __tablename__ = "bookmark_import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    source_type = Column(String(20), default="json", nullable=False)
    imported_count = Column(Integer, default=0)
    folder_count = Column(Integer, default=0, nullable=False)
    skipped_count = Column(Integer, default=0, nullable=False)
    duplicate_count = Column(Integer, default=0, nullable=False)
    dry_run = Column(Boolean, default=False, nullable=False)
    backup_id = Column(
        Integer,
        ForeignKey(
            "bookmark_backups.id",
            name="fk_bookmark_import_jobs_backup",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    report_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    user = relationship("User")
    backup = relationship("BookmarkBackup")


class SearchEngine(Base):
    __tablename__ = "search_engines"
    __table_args__ = (Index("ix_search_engines_user_order", "user_id", "sort_order"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    category = Column(String(50), nullable=False, default="general")
    category_label = Column(String(100), nullable=True)
    name = Column(String(100), nullable=False)
    url_template = Column(String(1000), nullable=False)
    icon = Column(String(100), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User")


class BookmarkExportJob(Base):
    __tablename__ = "bookmark_export_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    export_type = Column(String(20), default="json", nullable=False)
    exported_count = Column(Integer, default=0)
    file_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    user = relationship("User")


class BookmarkBackup(Base):
    __tablename__ = "bookmark_backups"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer, default=0)
    sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
