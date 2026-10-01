"""Private user playlists and their ordered imported/copied tracks."""

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
