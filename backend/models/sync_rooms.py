"""Shared synchronization room model."""

from .base import (
    Base,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
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
