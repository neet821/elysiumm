from __future__ import annotations


from typing import Literal
from schema_domains._base import BaseModel, Field, List, Optional, datetime
from schema_domains.identity import UserSimple

class SyncRoomBase(BaseModel):
    room_name: str
    mode: str = "url"  # url=外链, upload=上传, local=本地同步
    video_source: Optional[str] = None
    control_mode: str = "host_only"
    password: Optional[str] = None # 接收明文密码
    type: str = "video"


class SyncRoomCreate(SyncRoomBase):
    pass


class SyncRoomUpdate(BaseModel):
    room_name: Optional[str] = None
    mode: Optional[str] = None
    video_source: Optional[str] = None
    control_mode: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    auto_delete_file: Optional[bool] = None  # 管理员可控制是否删除文件


class SyncRoomLockUpdate(BaseModel):
    is_locked: bool


class SyncRoom(BaseModel):
    id: int
    room_code: str
    room_name: str
    host_user_id: int
    control_mode: str
    music_skip_vote_percent: int = 30
    mode: str
    video_source: Optional[str]
    video_filename: Optional[str] = None
    video_size: Optional[int] = None
    type: str = "video"
    is_active: bool
    is_locked: bool = False
    has_password: bool = False # 返回给前端是否加密
    expires_at: Optional[datetime]
    last_activity_at: Optional[datetime]
    created_at: datetime
    member_count: int = 0 # 返回人数

    class Config:
        from_attributes = True


class SyncRoomInfo(BaseModel):
    """房间详细信息(包含主机信息)"""
    id: int
    room_code: str
    room_name: str
    host_user_id: int
    host: Optional[UserSimple] = None
    control_mode: str
    music_skip_vote_percent: int = 30
    mode: str
    video_source: Optional[str]
    video_filename: Optional[str] = None
    video_size: Optional[int] = None
    video_hash: Optional[str] = None
    type: str = "video"
    current_time: float = 0
    is_playing: bool = False
    playback_version: int = 0
    current_queue_item_id: Optional[int] = None
    playback_started_at_server_ms: int = 0
    playback_rate: float = 1.0
    lifecycle_status: str = "active"
    is_active: bool
    is_deleted: bool = False
    has_password: bool = False
    expires_at: Optional[datetime]
    last_activity_at: Optional[datetime]
    deleted_at: Optional[datetime] = None
    is_locked: bool = False
    auto_delete_file: bool = True
    created_at: datetime
    updated_at: Optional[datetime]
    member_count: int = 0
    members: List['SyncRoomMemberInfo'] = []  # ← 添加成员列表字段

    class Config:
        from_attributes = True


class RoomSnapshotPayload(BaseModel):
    room_id: int
    track_id: Optional[int] = None
    media_id: Optional[int] = None
    state: str
    position: float
    started_at_server_ms: int
    playback_rate: float
    version: int
    server_now_ms: int


class RoomCoreSnapshotPayload(BaseModel):
    room_id: int
    media_kind: Optional[Literal["music", "video", "game"]] = None
    media_id: Optional[int] = None
    state: Literal["playing", "paused"]
    position: float
    started_at_server_ms: int
    playback_rate: float
    version: int
    server_now_ms: int


class VideoSubtitleInfo(BaseModel):
    id: int
    item_id: int
    label: str
    language: str
    format: Literal["vtt"] = "vtt"
    original_filename: str
    file_size: int
    src: str
    created_at: Optional[datetime] = None


class VideoPlaylistItemInfo(BaseModel):
    id: int
    room_id: int
    position: int
    source_type: Literal["external", "upload", "legacy_local"]
    title: str
    original_filename: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    duration_seconds: Optional[float] = None
    resolution: Optional[dict[str, int]] = None
    availability: Literal["available", "unavailable", "failed"]
    playback_url: Optional[str] = None
    subtitles: List[VideoSubtitleInfo] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VideoSessionInfo(BaseModel):
    room_id: int
    current_item_id: Optional[int] = None
    selected_subtitle_id: Optional[int] = None
    playlist: List[VideoPlaylistItemInfo] = Field(default_factory=list)


class MusicRoomEventInfo(BaseModel):
    id: int
    room_id: int
    actor_user_id: Optional[int] = None
    event_type: str
    playback_version: Optional[int] = None
    summary_json: str
    created_at: datetime

    class Config:
        from_attributes = True


class SyncRoomMemberInfo(BaseModel):
    """房间成员信息"""
    id: int
    user_id: int
    username: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None  # 🆕 头像URL
    is_verified: bool = True
    is_online: bool = False  # 添加在线状态字段
    joined_at: datetime

    class Config:
        from_attributes = True


class SyncRoomMessageCreate(BaseModel):
    """发送消息请求"""
    message: str
    is_private: bool = False  # 🔧 是否为私信
    target_user_id: Optional[int] = None  # 🔧 私信目标用户ID


class SyncRoomMessage(BaseModel):
    """聊天消息"""
    id: int
    room_id: int
    user_id: int
    username: str
    message: str
    is_private: bool = False  # 🔧 是否为私信
    target_user_id: Optional[int] = None  # 🔧 私信目标用户ID
    target_username: Optional[str] = None  # 🔧 私信目标用户名
    created_at: datetime

    class Config:
        from_attributes = True


class WSPlaybackControl(BaseModel):
    """播放控制消息"""
    action: str  # play, pause, seek, rate
    time: Optional[float] = None
    rate: Optional[float] = None


class WSChatMessage(BaseModel):
    """聊天消息"""
    message: str


class WSMemberUpdate(BaseModel):
    """成员更新消息"""
    action: str  # join, leave
    user_id: int
    username: str


class TransferHostRequest(BaseModel):
    """转让房主请求"""
    new_host_user_id: int


class KickMemberRequest(BaseModel):
    """踢出成员请求"""
    target_user_id: int
