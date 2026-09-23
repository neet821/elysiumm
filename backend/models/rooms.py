"""Rooms database models."""

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


class SyncRoom(Base):
    __tablename__ = "sync_rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(20), unique=True, index=True, nullable=False)  # 房间代码
    room_name = Column(String(100), nullable=False)
    host_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    control_mode = Column(
        String(20), default="host_only", nullable=False
    )  # host_only 或 all_members
    music_skip_vote_percent = Column(
        Integer,
        default=30,
        server_default="30",
        nullable=False,
    )
    mode = Column(
        String(20), default="url", nullable=False
    )  # url=外链, upload=上传到服务器, local=本地同步
    video_source = Column(Text, nullable=True)  # 视频链接或文件路径
    video_filename = Column(String(255), nullable=True)  # 上传的原始文件名
    video_size = Column(Integer, nullable=True)  # 文件大小（字节）
    video_hash = Column(String(64), nullable=True)  # 文件哈希值(local模式使用)

    type = Column(String(20), default="video", nullable=False)

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
    lifecycle_status = Column(
        String(20), default="active", nullable=False
    )  # active/idle/expired/closed/deleted
    is_active = Column(Boolean, default=True)  # 房间是否活跃
    is_deleted = Column(Boolean, default=False, nullable=False)  # 软删除标记
    password_hash = Column(String(255), nullable=True)  # 房间密码，为空则公开
    expires_at = Column(DateTime, nullable=True)  # 自动关闭时间
    last_activity_at = Column(DateTime, default=datetime.utcnow)  # 最后有人活动的时间
    deleted_at = Column(DateTime, nullable=True)  # 软删除时间
    is_locked = Column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )  # 管理员锁定后不参与自动清理
    auto_delete_file = Column(
        Boolean, default=True
    )  # 是否随房间删除文件（管理员可设为False）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    host = relationship("User")
    members = relationship(
        "SyncRoomMember", back_populates="room", cascade="all, delete-orphan"
    )
    messages = relationship(
        "SyncRoomMessage", back_populates="room", cascade="all, delete-orphan"
    )
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


class SyncRoomMessage(Base):
    __tablename__ = "sync_room_messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    is_private = Column(Boolean, default=False)  # 🔧 是否为私信
    target_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # 🔧 私信目标用户
    created_at = Column(DateTime, default=datetime.utcnow)

    room = relationship("SyncRoom", back_populates="messages")
    user = relationship("User", foreign_keys=[user_id])
    target_user = relationship(
        "User", foreign_keys=[target_user_id]
    )  # 🔧 私信目标用户关系
