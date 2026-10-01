from __future__ import annotations


from schema_domains._base import BaseModel, List, Optional, datetime

class SyncDeviceSummary(BaseModel):
    id: int
    name: str
    token_hint: str
    token_expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    rotated_at: Optional[datetime] = None
    root_name: str
    status: str
    is_paused: bool
    scan_requested: bool
    last_seen_at: Optional[datetime] = None
    created_at: datetime


class SyncDeviceSecretResponse(SyncDeviceSummary):
    device_token: str


class SyncFileSummary(BaseModel):
    id: int
    device_id: int
    relative_path: str
    file_name: str
    file_size: int
    sha256: Optional[str] = None
    mtime: Optional[datetime] = None
    sync_status: str
    bytes_transferred: int
    expected_size: int
    progress_percent: int
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SyncEventSummary(BaseModel):
    id: int
    device_id: int
    relative_path: Optional[str] = None
    event_type: str
    status: str
    bytes_transferred: int
    created_at: datetime


class SyncDashboardResponse(BaseModel):
    devices: List[SyncDeviceSummary]
    files: List[SyncFileSummary]
    events: List[SyncEventSummary]
