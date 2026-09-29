"""Canonical music identity, provider mappings, sources, and lyrics models."""

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
