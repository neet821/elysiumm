"""Video room playlist, subtitle, and session models."""

from .base import (
    Base,
    BigInteger,
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


class VideoPlaylistItem(Base):
    __tablename__ = "video_playlist_items"
    __table_args__ = (
        UniqueConstraint("room_id", "position", name="uq_video_playlist_room_position"),
        CheckConstraint("position >= 0", name="ck_video_playlist_position_nonnegative"),
        CheckConstraint(
            "source_type IN ('external', 'upload', 'legacy_local')",
            name="ck_video_playlist_source_type",
        ),
        CheckConstraint(
            "availability IN ('available', 'unavailable', 'failed')",
            name="ck_video_playlist_availability",
        ),
        CheckConstraint(
            "file_size IS NULL OR file_size >= 0",
            name="ck_video_playlist_file_size_nonnegative",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_video_playlist_duration_nonnegative",
        ),
        Index("ix_video_playlist_items_room_position", "room_id", "position"),
    )

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(
        Integer,
        ForeignKey("sync_rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    position = Column(Integer, default=0, server_default="0", nullable=False)
    source_type = Column(String(20), nullable=False)
    source_url = Column(Text, nullable=True)
    storage_path = Column(Text, nullable=True)
    original_filename = Column(String(255), nullable=True)
    title = Column(String(255), nullable=False)
    content_type = Column(String(120), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    local_fingerprint = Column(String(64), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    availability = Column(
        String(20),
        default="available",
        server_default="available",
        nullable=False,
    )
    owned_file = Column(Boolean, default=False, server_default="0", nullable=False)
    temporary_upload = Column(
        Boolean, default=False, server_default="0", nullable=False
    )
    created_by = Column(
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

    room = relationship("SyncRoom", foreign_keys=[room_id])
    creator = relationship("User", foreign_keys=[created_by])
    subtitles = relationship(
        "VideoSubtitle",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="VideoSubtitle.id",
    )


class VideoSubtitle(Base):
    __tablename__ = "video_subtitles"
    __table_args__ = (
        CheckConstraint(
            "file_size >= 0", name="ck_video_subtitle_file_size_nonnegative"
        ),
        Index("ix_video_subtitles_item_id", "item_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(
        Integer,
        ForeignKey("video_playlist_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    label = Column(String(80), nullable=False)
    language = Column(String(35), nullable=False)
    format = Column(String(10), default="vtt", server_default="vtt", nullable=False)
    storage_path = Column(Text, nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    item = relationship("VideoPlaylistItem", back_populates="subtitles")
    creator = relationship("User", foreign_keys=[created_by])


class VideoSession(Base):
    __tablename__ = "video_sessions"

    room_id = Column(
        Integer,
        ForeignKey("sync_rooms.id", ondelete="CASCADE"),
        primary_key=True,
    )
    current_item_id = Column(
        Integer,
        ForeignKey(
            "video_playlist_items.id",
            name="fk_video_sessions_current_item_id_video_playlist_items",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    selected_subtitle_id = Column(
        Integer,
        ForeignKey(
            "video_subtitles.id",
            name="fk_video_sessions_selected_subtitle_id_video_subtitles",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    room = relationship(
        "SyncRoom",
        back_populates="video_session",
        foreign_keys=[room_id],
    )
    current_item = relationship(
        "VideoPlaylistItem",
        foreign_keys=[current_item_id],
        post_update=True,
    )
    selected_subtitle = relationship(
        "VideoSubtitle",
        foreign_keys=[selected_subtitle_id],
        post_update=True,
    )
