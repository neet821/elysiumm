"""Music database models."""

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


class CanonicalTrack(Base):
    __tablename__ = "canonical_tracks"
    __table_args__ = (
        Index(
            "ix_canonical_tracks_identity",
            "normalized_title",
            "normalized_artist",
            "duration_seconds",
            mysql_length={"normalized_title": 255, "normalized_artist": 255},
        ),
        Index("ix_canonical_tracks_isrc", "isrc"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    normalized_title = Column(String(300), nullable=False)
    primary_artist = Column(String(500), nullable=False)
    normalized_artist = Column(String(500), nullable=False)
    album = Column(String(300), nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    isrc = Column(String(32), nullable=True)
    artwork_url = Column(String(1000), nullable=True)
    availability = Column(String(20), default="unavailable", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    provider_mappings = relationship(
        "TrackProviderMapping",
        back_populates="canonical_track",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audio_sources = relationship(
        "TrackAudioSource",
        back_populates="canonical_track",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    lyrics = relationship(
        "TrackLyrics",
        back_populates="canonical_track",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TrackProviderMapping(Base):
    __tablename__ = "track_provider_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_track_id",
            name="uq_track_provider_identity",
        ),
        Index("ix_track_provider_mappings_canonical", "canonical_track_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    canonical_track_id = Column(
        Integer,
        ForeignKey("canonical_tracks.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider = Column(String(30), nullable=False)
    provider_track_id = Column(String(255), nullable=False)
    media_mid = Column(String(255), nullable=True)
    fee = Column(Integer, nullable=True)
    region = Column(String(50), nullable=True)
    availability = Column(String(20), default="unavailable", nullable=False)
    metadata_json = Column(Text, default="{}", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    canonical_track = relationship(
        "CanonicalTrack",
        back_populates="provider_mappings",
    )


class TrackAudioSource(Base):
    __tablename__ = "track_audio_sources"
    __table_args__ = (
        Index("ix_track_audio_sources_expires_at", "expires_at"),
        Index(
            "ix_track_audio_sources_lookup",
            "canonical_track_id",
            "availability",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    canonical_track_id = Column(
        Integer,
        ForeignKey("canonical_tracks.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_mapping_id = Column(
        Integer,
        ForeignKey("track_provider_mappings.id", ondelete="CASCADE"),
        nullable=True,
    )
    source_type = Column(String(40), nullable=False)
    playback_url = Column(Text, nullable=True)
    availability = Column(String(20), default="unavailable", nullable=False)
    expires_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    canonical_track = relationship("CanonicalTrack", back_populates="audio_sources")


class TrackLyrics(Base):
    __tablename__ = "track_lyrics"
    __table_args__ = (
        UniqueConstraint(
            "canonical_track_id",
            "provider",
            "language",
            name="uq_track_lyrics_identity",
        ),
        Index("ix_track_lyrics_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    canonical_track_id = Column(
        Integer,
        ForeignKey("canonical_tracks.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_mapping_id = Column(
        Integer,
        ForeignKey("track_provider_mappings.id", ondelete="CASCADE"),
        nullable=True,
    )
    provider = Column(String(30), nullable=False)
    language = Column(String(30), default="original", nullable=False)
    timed_text = Column(Text, nullable=True)
    translation_text = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    canonical_track = relationship("CanonicalTrack", back_populates="lyrics")


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


class UserPlaylist(Base):
    """A private, user-owned playlist or immutable copy of a public source."""

    __tablename__ = "user_playlists"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "source_provider",
            "source_playlist_id",
            name="uq_user_playlist_import_source",
        ),
        Index("ix_user_playlists_owner_updated", "owner_user_id", "updated_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(120), nullable=False)
    source_provider = Column(String(30), nullable=True)
    source_playlist_id = Column(String(64), nullable=True)
    source_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    items = relationship(
        "UserPlaylistItem",
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="UserPlaylistItem.position",
        passive_deletes=True,
    )


class UserPlaylistItem(Base):
    """Ordered snapshot row; copied metadata survives source changes/removals."""

    __tablename__ = "user_playlist_items"
    __table_args__ = (
        UniqueConstraint("playlist_id", "position", name="uq_user_playlist_position"),
        Index("ix_user_playlist_items_canonical", "canonical_track_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    playlist_id = Column(
        Integer,
        ForeignKey("user_playlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    canonical_track_id = Column(
        Integer,
        ForeignKey("canonical_tracks.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider = Column(String(30), default="netease", nullable=False)
    provider_track_id = Column(String(120), nullable=True)
    title = Column(String(300), nullable=False)
    artist = Column(String(500), nullable=False)
    album = Column(String(300), nullable=True)
    artwork_url = Column(Text, nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    availability = Column(String(20), default="unavailable", nullable=False)
    position = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    playlist = relationship("UserPlaylist", back_populates="items")
