from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import relationship, backref
from datetime import datetime
import uuid
from database import Base

# 文章标签关联表
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id")),
    Column("tag_id", Integer, ForeignKey("tags.id"))
)

# 照片标签关联表
photo_tags = Table(
    "photo_tags",
    Base.metadata,
    Column("photo_id", Integer, ForeignKey("photos.id")),
    Column("tag_id", Integer, ForeignKey("tags.id"))
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    avatar = Column(String(500), nullable=True)  # 🆕 头像URL
    role = Column(String(20), default="user", nullable=False)  # 'admin' 或 'user'
    is_active = Column(Boolean, default=True, nullable=False)  # 账号是否启用
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    posts = relationship("Post", back_populates="author")

class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), nullable=False, default="database")
    status = Column(String(20), nullable=False, default="running")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    summary_json = Column(Text, nullable=True)

    creator = relationship("User")
    files = relationship("BackupFile", back_populates="job", cascade="all, delete-orphan")

class BackupFile(Base):
    __tablename__ = "backup_files"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("backup_jobs.id"), nullable=False)
    type = Column(String(50), nullable=False, default="database")
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("BackupJob", back_populates="files")

class RestoreJob(Base):
    __tablename__ = "restore_jobs"

    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    backup_file_id = Column(
        Integer,
        ForeignKey("backup_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_filename = Column(String(255), nullable=True)
    source_sha256 = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    rollback_status = Column(String(20), nullable=False, default="not_attempted")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    backup_file = relationship("BackupFile")
    creator = relationship("User")

class AdminFile(Base):
    __tablename__ = "admin_files"

    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(80), unique=True, index=True, nullable=False)
    content_type = Column(String(120), nullable=False)
    file_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    uploader = relationship("User")

class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(80), nullable=False, index=True)
    resource_type = Column(String(80), nullable=False)
    resource_id = Column(String(128), nullable=True)
    outcome = Column(String(20), nullable=False, default="success", index=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User")

class HomepageSetting(Base):
    __tablename__ = "homepage_settings"

    id = Column(Integer, primary_key=True)
    config_json = Column(Text, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    updater = relationship("User")

class RealtimeEventAuditLog(Base):
    __tablename__ = "realtime_event_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_name = Column(String(80), nullable=False, index=True)
    room_id = Column(Integer, nullable=True, index=True)
    outcome = Column(String(20), nullable=False, default="success", index=True)
    detail = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    actor = relationship("User")

class FrpOperationLog(Base):
    __tablename__ = "frp_operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="completed")
    message = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User")


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
    recording_enabled = Column(Boolean, nullable=False, default=True)
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


class SyncDevice(Base):
    __tablename__ = "sync_devices"
    __table_args__ = (
        UniqueConstraint("device_token_hash", name="uq_sync_device_token_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    device_token_hash = Column(String(64), index=True, nullable=False)
    token_hint = Column(String(12), nullable=False)
    token_expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    rotated_at = Column(DateTime, nullable=True)
    root_name = Column(String(100), default="Public", nullable=False)
    status = Column(String(20), default="offline", nullable=False)
    is_paused = Column(Boolean, default=False, nullable=False)
    scan_requested = Column(Boolean, default=False, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class SyncFile(Base):
    __tablename__ = "sync_files"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "relative_path",
            name="uq_sync_file_device_path",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("sync_devices.id"), nullable=False)
    relative_path = Column(String(1000), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    sha256 = Column(String(64), nullable=True)
    mtime = Column(DateTime, nullable=True)
    sync_status = Column(String(20), default="synced", nullable=False)
    bytes_transferred = Column(Integer, default=0, nullable=False)
    expected_size = Column(Integer, default=0, nullable=False)
    progress_percent = Column(Integer, default=100, nullable=False)
    storage_path = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device = relationship("SyncDevice")


class SyncUpload(Base):
    __tablename__ = "sync_uploads"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "upload_id",
            name="uq_sync_upload_device_upload_id",
        ),
        CheckConstraint("expected_size >= 0", name="ck_sync_upload_expected_size"),
        CheckConstraint("total_chunks > 0", name="ck_sync_upload_total_chunks"),
        CheckConstraint("received_chunks >= 0", name="ck_sync_upload_received_chunks"),
        CheckConstraint("received_bytes >= 0", name="ck_sync_upload_received_bytes"),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(
        Integer,
        ForeignKey("sync_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    upload_id = Column(String(64), nullable=False)
    relative_path = Column(String(1000), nullable=False)
    expected_size = Column(BigInteger, nullable=False)
    expected_sha256 = Column(String(64), nullable=True)
    total_chunks = Column(Integer, nullable=False)
    received_chunks = Column(Integer, default=0, nullable=False)
    received_chunks_json = Column(Text, default="[]", nullable=False)
    received_bytes = Column(BigInteger, default=0, nullable=False)
    status = Column(String(20), default="uploading", nullable=False, index=True)
    temp_path = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    device = relationship("SyncDevice")

class SyncEvent(Base):
    __tablename__ = "sync_events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("sync_devices.id"), nullable=False)
    relative_path = Column(String(1000), nullable=True)
    event_type = Column(String(30), nullable=False)
    status = Column(String(20), default="completed", nullable=False)
    message = Column(Text, nullable=True)
    bytes_transferred = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    device = relationship("SyncDevice")


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

class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(80), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    cover = Column(String(500), nullable=True)
    category = Column(String(50), default="turn_based", nullable=False)
    min_players = Column(Integer, default=2, nullable=False)
    max_players = Column(Integer, default=2, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    rules_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class GameRoom(Base):
    __tablename__ = "game_rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(12), unique=True, index=True, nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    status = Column(String(20), default="waiting", nullable=False)
    visibility = Column(String(20), default="public", nullable=False)
    max_players = Column(Integer, default=2, nullable=False)
    room_version = Column(Integer, default=0, nullable=False)
    password_hash = Column(String(255), nullable=True)
    allow_spectators = Column(Boolean, default=True, nullable=False)
    settings_json = Column(Text, default='{"turn_timeout_seconds":90}', nullable=False)
    current_turn_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expired_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    game = relationship("Game")
    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("GameRoomMember", back_populates="room", cascade="all, delete-orphan")

class GameRoomMember(Base):
    __tablename__ = "game_room_members"
    __table_args__ = (
        CheckConstraint(
            "role IN ('player', 'spectator')",
            name="ck_game_room_member_role",
        ),
        UniqueConstraint("room_id", "user_id", name="uq_game_room_member_user"),
        UniqueConstraint("room_id", "seat", name="uq_game_room_member_seat"),
    )

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("game_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seat = Column(Integer, nullable=True)
    symbol = Column(String(10), nullable=True)
    role = Column(String(20), default="player", nullable=False)
    is_ready = Column(Boolean, default=False, nullable=False)
    is_online = Column(Boolean, default=True, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    ready_at = Column(DateTime, nullable=True)
    left_at = Column(DateTime, nullable=True)

    room = relationship("GameRoom", back_populates="members")
    user = relationship("User")

class GameState(Base):
    __tablename__ = "game_states"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("game_rooms.id"), nullable=False, unique=True)
    version = Column(Integer, default=0, nullable=False)
    state_json = Column(Text, nullable=False)
    state_hash = Column(String(64), default="0" * 64, nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    turn_started_at = Column(DateTime, nullable=True)
    turn_deadline_at = Column(DateTime, nullable=True)
    draw_offer_user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_game_states_draw_offer_user_id_users",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class GameEvent(Base):
    __tablename__ = "game_events"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("game_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type = Column(String(40), nullable=False)
    payload_json = Column(Text, nullable=True)
    version = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class GameReplayFrame(Base):
    __tablename__ = "game_replay_frames"
    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_game_replay_version_nonnegative"),
        UniqueConstraint("room_id", "version", name="uq_game_replay_room_version"),
        Index("ix_game_replay_room_version", "room_id", "version"),
    )

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("game_rooms.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(40), nullable=False)
    action_json = Column(Text, nullable=False)
    state_json = Column(Text, nullable=False)
    state_hash = Column(String(64), nullable=False)
    previous_hash = Column(String(64), nullable=True)
    frame_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class GameInvite(Base):
    __tablename__ = "game_invites"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("game_rooms.id"), nullable=False)
    token = Column(String(64), unique=True, index=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class GameResult(Base):
    __tablename__ = "game_results"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("game_rooms.id"), nullable=False)
    winner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    result_json = Column(Text, nullable=False)
    final_version = Column(Integer, default=0, nullable=False)
    final_frame_hash = Column(String(64), nullable=True)
    reason = Column(String(30), default="legacy", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    category = Column(String(50), nullable=True, default="未分类")
    views = Column(Integer, default=0)  # 浏览次数
    slug = Column(String(200), unique=True, index=True, nullable=True)  # 🆕 URL Slug
    pin_priority = Column(Integer, default=0)  # 🆕 置顶优先级 (0=无, 1=低, 2=中, 3=高)
    is_hidden = Column(Boolean, default=False)  # 🆕 是否隐藏
    author_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    author = relationship("User", back_populates="posts")
    tags = relationship("Tag", secondary=post_tags, back_populates="posts")

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    color = Column(String(20), default="blue")  # 标签颜色
    created_at = Column(DateTime, default=datetime.utcnow)

    posts = relationship("Post", secondary=post_tags, back_populates="tags")
    photos = relationship("Photo", secondary=photo_tags, back_populates="tags")

class LinkCategory(Base):
    __tablename__ = "link_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    description = Column(String(200), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    links = relationship("WebsiteLink", back_populates="category", cascade="all, delete-orphan")

class WebsiteLink(Base):
    __tablename__ = "website_links"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    description = Column(String(300), nullable=True)
    category_id = Column(Integer, ForeignKey("link_categories.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("LinkCategory", back_populates="links")
    user = relationship("User")

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
    tag_relations = relationship("BookmarkTagRelation", back_populates="bookmark", cascade="all, delete-orphan")

class BookmarkTag(Base):
    __tablename__ = "bookmark_tags"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    bookmark_relations = relationship("BookmarkTagRelation", back_populates="tag", cascade="all, delete-orphan")

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
    __table_args__ = (
        Index("ix_search_engines_user_order", "user_id", "sort_order"),
    )

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

# 同步观影房间表
class SyncRoom(Base):
    __tablename__ = "sync_rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(20), unique=True, index=True, nullable=False)  # 房间代码
    room_name = Column(String(100), nullable=False)
    host_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    control_mode = Column(String(20), default="host_only", nullable=False)  # host_only 或 all_members
    mode = Column(String(20), default="url", nullable=False)  # url=外链, upload=上传到服务器, local=本地同步
    video_source = Column(Text, nullable=True)  # 视频链接或文件路径
    video_filename = Column(String(255), nullable=True)  # 上传的原始文件名
    video_size = Column(Integer, nullable=True)  # 文件大小（字节）
    video_hash = Column(String(64), nullable=True)  # 文件哈希值(local模式使用)

    # Game Room Fields
    type = Column(String(20), default="video", nullable=False) # 'video' or 'game'
    game_type = Column(String(50), nullable=True) # e.g. 'gomoku', 'uno'
    game_state = Column(Text, nullable=True) # JSON string for game state

    current_time = Column(Float, default=0)  # 当前播放时间(秒)
    is_playing = Column(Boolean, default=False)  # 播放状态
    playback_version = Column(Integer, default=0, nullable=False)  # 播放状态版本号
    current_queue_item_id = Column(
        Integer,
        ForeignKey(
            "music_queue_items.id",
            name="fk_sync_rooms_current_queue_item_id_music_queue_items",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    playback_started_at_server_ms = Column(
        BigInteger,
        default=0,
        server_default="0",
        nullable=False,
    )
    playback_rate = Column(
        Float,
        default=1.0,
        server_default="1.0",
        nullable=False,
    )
    lifecycle_status = Column(String(20), default="active", nullable=False)  # active/idle/expired/closed/deleted
    is_active = Column(Boolean, default=True)  # 房间是否活跃
    is_deleted = Column(Boolean, default=False, nullable=False)  # 软删除标记
    password_hash = Column(String(255), nullable=True) # 房间密码，为空则公开
    expires_at = Column(DateTime, nullable=True) # 自动关闭时间
    last_activity_at = Column(DateTime, default=datetime.utcnow)  # 最后有人活动的时间
    deleted_at = Column(DateTime, nullable=True)  # 软删除时间
    auto_delete_file = Column(Boolean, default=True)  # 是否随房间删除文件（管理员可设为False）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    host = relationship("User")
    members = relationship("SyncRoomMember", back_populates="room", cascade="all, delete-orphan")
    messages = relationship("SyncRoomMessage", back_populates="room", cascade="all, delete-orphan")
    music_events = relationship(
        "MusicRoomEvent",
        back_populates="room",
        cascade="all, delete-orphan",
    )
    video_session = relationship(
        "VideoSession",
        back_populates="room",
        cascade="all, delete-orphan",
        uselist=False,
        foreign_keys="VideoSession.room_id",
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
        CheckConstraint("file_size >= 0", name="ck_video_subtitle_file_size_nonnegative"),
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

class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(500), nullable=False)
    caption = Column(String(200), nullable=True)  # 注释
    location = Column(String(100), nullable=True)  # 地点
    is_featured = Column(Boolean, default=False)   # 是否在首页展示
    created_at = Column(DateTime, default=datetime.utcnow)

    tags = relationship("Tag", secondary=photo_tags, back_populates="photos")

    # 如果需要关联用户（上传者）
    # user_id = Column(Integer, ForeignKey("users.id"))
    # user = relationship("User")

# 房间成员表
class SyncRoomMember(Base):
    __tablename__ = "sync_room_members"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    nickname = Column(String(50), nullable=True)  # 房间内昵称
    is_verified = Column(Boolean, default=True)  # 是否通过哈希校验(模式二使用)
    is_online = Column(Boolean, default=True)  # 是否在线
    last_active_at = Column(DateTime, default=datetime.utcnow)  # 最后活跃时间
    joined_at = Column(DateTime, default=datetime.utcnow)

    room = relationship("SyncRoom", back_populates="members")
    user = relationship("User")

# 房间聊天消息表
class SyncRoomMessage(Base):
    __tablename__ = "sync_room_messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    is_private = Column(Boolean, default=False)  # 🔧 是否为私信
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 🔧 私信目标用户
    created_at = Column(DateTime, default=datetime.utcnow)

    room = relationship("SyncRoom", back_populates="messages")
    user = relationship("User", foreign_keys=[user_id])
    target_user = relationship("User", foreign_keys=[target_user_id])  # 🔧 私信目标用户关系


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
    __table_args__ = (
        Index("ix_music_room_events_room_id_id", "room_id", "id"),
    )

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
    __table_args__ = (UniqueConstraint("queue_item_id", "user_id", name="uq_music_skip_vote"),)

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False, index=True)
    queue_item_id = Column(Integer, ForeignKey("music_queue_items.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MusicTrackVote(Base):
    __tablename__ = "music_track_votes"
    __table_args__ = (UniqueConstraint("queue_item_id", "user_id", name="uq_music_track_vote"),)

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False, index=True)
    queue_item_id = Column(Integer, ForeignKey("music_queue_items.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MusicFavorite(Base):
    __tablename__ = "music_favorites"
    __table_args__ = (UniqueConstraint("user_id", "provider", "provider_track_id", name="uq_music_favorite"),)

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

class MessageBoard(Base):
    __tablename__ = "message_board"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("message_board.id"), nullable=True) # 🆕
    likes = Column(Integer, default=0) # 🆕
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    replies = relationship("MessageBoard", backref=backref('parent', remote_side=[id])) # 🆕

class MessageLike(Base):
    __tablename__ = "message_likes"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("message_board.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ResourceRequest(Base):
    __tablename__ = "resource_requests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending, completed, invalid, abandoned
    is_anonymous = Column(Boolean, default=False) # 🆕
    is_private = Column(Boolean, default=False) # 🆕

    # Fulfillment details
    reply_content = Column(Text, nullable=True)  # Admin reply
    file_url = Column(String(500), nullable=True)  # Uploaded file URL
    external_link = Column(String(500), nullable=True)  # External link
    expires_at = Column(DateTime, nullable=True)  # File expiration

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    replies = relationship("WishlistReply", back_populates="request", cascade="all, delete-orphan") # 🆕

class WishlistReply(Base): # 🆕
    __tablename__ = "wishlist_replies"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    request_id = Column(Integer, ForeignKey("resource_requests.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    request = relationship("ResourceRequest", back_populates="replies")
    user = relationship("User")
