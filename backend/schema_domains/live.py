from __future__ import annotations


from typing import Literal
from schema_domains._base import BaseModel, Field, List, Optional, datetime, field_validator

class LiveStatusResponse(BaseModel):
    status: Literal["waiting", "live", "ended", "unavailable"]
    title: str
    description: str
    cover_url: Optional[str] = None
    access_mode: Literal["public", "allowlist", "invite"]
    stream_quality: Literal["smooth", "balanced", "clear", "source"]
    target_bitrate_kbps: Optional[int] = None
    latency_mode: Literal["normal", "low", "ultra_low"]
    started_at: Optional[datetime] = None


class LiveSessionCreateRequest(BaseModel):
    invite_token: Optional[str] = Field(default=None, max_length=512)


class LiveViewerSessionResponse(BaseModel):
    viewer_session_id: str
    live_session_id: int
    media_url: str
    expires_in: int


class LiveHeartbeatResponse(BaseModel):
    viewer_session_id: str
    watched_seconds: int
    expires_in: int


class MediaMtxAuthRequest(BaseModel):
    action: Literal["publish", "read", "playback", "api", "metrics", "pprof"]
    path: str = Field(default="", max_length=500)
    token: Optional[str] = Field(default=None, max_length=512)
    user: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=512)
    protocol: Optional[str] = Field(default=None, max_length=32)


class LiveAdminSettingsUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)
    cover_url: Optional[str] = Field(default=None, max_length=500)
    access_mode: Literal["public", "allowlist", "invite"]
    viewing_enabled: bool
    recording_enabled: bool
    stream_quality: Optional[Literal["smooth", "balanced", "clear", "source"]] = None
    target_bitrate_kbps: Optional[int] = Field(default=None, ge=300, le=50000)
    latency_mode: Optional[Literal["normal", "low", "ultra_low"]] = None
    revision: int = Field(ge=1)


class LiveAllowedUsersUpdate(BaseModel):
    user_ids: List[int] = Field(default_factory=list, max_length=500)


class LiveInviteCreateRequest(BaseModel):
    expires_in_hours: Optional[int] = Field(default=24, ge=1, le=24 * 365)


class LiveRecordingUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class LiveRecordingCompleteRequest(BaseModel):
    absolute_path: str = Field(min_length=1, max_length=1200)
    duration_seconds: float = Field(default=0, ge=0, le=24 * 60 * 60)


class LiveMessageCreateRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=300)

    @field_validator("nickname", "content")
    @classmethod
    def trim_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("内容不能为空")
        return normalized
