"""Room queue, history, voting, and saved-music models."""

from .base import (
    Base,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    datetime,
    relationship,
)


class MusicQueueItem(Base):
    __tablename__ = "music_queue_items"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False, index=True)
    added_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    canonical_track_id = Column(
        Integer,
        ForeignKey("canonical_tracks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider = Column(String(30), default="audius", nullable=False)
    provider_track_id = Column(String(120), nullable=False)
    title = Column(String(255), nullable=False)
    artist = Column(String(255), nullable=False)
    album = Column(String(255), nullable=True)
    artwork_url = Column(Text, nullable=True)
    stream_url = Column(Text, nullable=False)
    duration_seconds = Column(Integer, default=0, nullable=False)
    source_url = Column(Text, nullable=True)
    status = Column(String(20), default="queued", nullable=False, index=True)
    position = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    played_at = Column(DateTime, nullable=True)

    user = relationship("User")


class MusicRoomEvent(Base):
    __tablename__ = "music_room_events"
    __table_args__ = (Index("ix_music_room_events_room_id_id", "room_id", "id"),)

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(
        Integer,
        ForeignKey("sync_rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type = Column(String(40), nullable=False)
    playback_version = Column(Integer, nullable=True)
    summary_json = Column(Text, default="{}", server_default="{}", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    room = relationship("SyncRoom", back_populates="music_events")
    actor = relationship("User")


class MusicSkipVote(Base):
    __tablename__ = "music_skip_votes"
    __table_args__ = (
        UniqueConstraint("queue_item_id", "user_id", name="uq_music_skip_vote"),
    )

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False, index=True)
    queue_item_id = Column(Integer, ForeignKey("music_queue_items.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MusicTrackVote(Base):
    __tablename__ = "music_track_votes"
    __table_args__ = (
        UniqueConstraint("queue_item_id", "user_id", name="uq_music_track_vote"),
    )

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False, index=True)
    queue_item_id = Column(
        Integer, ForeignKey("music_queue_items.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MusicFavorite(Base):
    __tablename__ = "music_favorites"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "provider_track_id", name="uq_music_favorite"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(30), default="audius", nullable=False)
    provider_track_id = Column(String(120), nullable=False)
    title = Column(String(255), nullable=False)
    artist = Column(String(255), nullable=False)
    album = Column(String(255), nullable=True)
    artwork_url = Column(Text, nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    source_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
