"""Live database models."""

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
    uuid,
)


class LiveSetting(Base):
    __tablename__ = "live_settings"
    __table_args__ = (
        CheckConstraint(
            "access_mode IN ('public', 'allowlist', 'invite')",
            name="ck_live_settings_access_mode",
        ),
        CheckConstraint(
            "stream_quality IN ('smooth', 'balanced', 'clear', 'source')",
            name="ck_live_settings_stream_quality",
        ),
        CheckConstraint(
            "latency_mode IN ('normal', 'low', 'ultra_low')",
            name="ck_live_settings_latency_mode",
        ),
    )

    id = Column(Integer, primary_key=True)
    title = Column(String(160), nullable=False, default="Blue Album 直播")
    description = Column(Text, nullable=False, default="")
    cover_url = Column(String(500), nullable=True)
    access_mode = Column(String(20), nullable=False, default="public")
    viewing_enabled = Column(Boolean, nullable=False, default=True)
    recording_enabled = Column(Boolean, nullable=False, default=False)
    stream_quality = Column(String(20), nullable=False, default="balanced")
    target_bitrate_kbps = Column(Integer, nullable=True)
    latency_mode = Column(String(20), nullable=False, default="normal")
    revision = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    updater = relationship("User")


class LiveCredential(Base):
    __tablename__ = "live_credentials"

    id = Column(Integer, primary_key=True)
    kind = Column(String(20), nullable=False, unique=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    token_hint = Column(String(12), nullable=False)
    rotated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    creator = relationship("User")


class LiveAllowedUser(Base):
    __tablename__ = "live_allowed_users"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    added_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    adder = relationship("User", foreign_keys=[added_by])


class LiveInvite(Base):
    __tablename__ = "live_invites"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    token_hint = Column(String(12), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    creator = relationship("User")


class LiveSession(Base):
    __tablename__ = "live_sessions"
    __table_args__ = (
        CheckConstraint(
            "access_mode IN ('public', 'allowlist', 'invite')",
            name="ck_live_sessions_access_mode",
        ),
        CheckConstraint(
            "status IN ('live', 'ended', 'failed')",
            name="ck_live_sessions_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    title = Column(String(160), nullable=False)
    description = Column(Text, nullable=False, default="")
    cover_url = Column(String(500), nullable=True)
    access_mode = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="live", index=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    publisher_last_seen_at = Column(DateTime, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    frame_rate = Column(Float, nullable=True)
    bit_rate = Column(BigInteger, nullable=True)
    video_codec = Column(String(32), nullable=True)
    audio_codec = Column(String(32), nullable=True)
    error_summary = Column(String(255), nullable=True)

    recordings = relationship(
        "LiveRecording",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    viewers = relationship(
        "LiveViewerSession",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class LiveRecording(Base):
    __tablename__ = "live_recordings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'ready', 'missing', 'failed')",
            name="ck_live_recordings_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    session_id = Column(
        Integer,
        ForeignKey("live_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name = Column(String(255), nullable=False)
    relative_path = Column(String(700), nullable=False, unique=True)
    file_size = Column(BigInteger, nullable=False, default=0)
    duration_seconds = Column(Float, nullable=False, default=0)
    sha256 = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="processing", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ready_at = Column(DateTime, nullable=True)
    remote_provider = Column(String(50), nullable=True)
    remote_file_id = Column(String(255), nullable=True)

    session = relationship("LiveSession", back_populates="recordings")


class LiveViewerSession(Base):
    __tablename__ = "live_viewer_sessions"
    __table_args__ = (
        CheckConstraint(
            "watched_seconds >= 0",
            name="ck_live_viewer_sessions_watched_seconds",
        ),
        UniqueConstraint(
            "live_session_id",
            "ip_address",
            name="uq_live_viewer_sessions_session_ip",
        ),
        Index(
            "ix_live_viewer_sessions_session_seen",
            "live_session_id",
            "last_seen_at",
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    live_session_id = Column(
        Integer,
        ForeignKey("live_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    invite_id = Column(
        Integer,
        ForeignKey("live_invites.id", ondelete="SET NULL"),
        nullable=True,
    )
    ip_address = Column(String(45), nullable=False)
    country = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    device_type = Column(String(32), nullable=True)
    operating_system = Column(String(100), nullable=True)
    browser = Column(String(100), nullable=True)
    first_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    watched_seconds = Column(Integer, nullable=False, default=0)
    ended_at = Column(DateTime, nullable=True)

    session = relationship("LiveSession", back_populates="viewers")
    user = relationship("User")
    invite = relationship("LiveInvite")


class LiveMessage(Base):
    __tablename__ = "live_messages"
    __table_args__ = (
        Index(
            "ix_live_messages_session_created",
            "live_session_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    live_session_id = Column(
        Integer,
        ForeignKey("live_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    viewer_session_id = Column(
        String(36),
        ForeignKey("live_viewer_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    nickname = Column(String(40), nullable=False)
    content = Column(String(300), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("LiveSession")
    viewer = relationship("LiveViewerSession")
