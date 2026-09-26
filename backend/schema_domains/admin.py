from __future__ import annotations


from schema_domains._base import BaseModel, List, Optional, datetime

class AdminAuditEvidence(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_username: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    outcome: str
    created_at: datetime


class RealtimeAuditEvidence(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_username: Optional[str] = None
    event_name: str
    room_id: Optional[int] = None
    outcome: str
    created_at: datetime


class AdminOverviewHealth(BaseModel):
    status: str
    database: str
    storage: str


class AdminOverviewUsers(BaseModel):
    total: int
    active: int
    inactive: int
    administrators: int


class AdminOverviewRooms(BaseModel):
    media_active: int


class AdminOverviewFiles(BaseModel):
    manual_count: int
    manual_bytes: int
    synced_count: int
    synced_bytes: int
    active_uploads: int


class AdminOverviewSync(BaseModel):
    devices: int
    online: int
    paused: int
    revoked: int
    expired: int


class AdminOverviewBooks(BaseModel):
    total: int
    published: int
    lists: int


class AdminOverviewResponse(BaseModel):
    generated_at: datetime
    health: AdminOverviewHealth
    users: AdminOverviewUsers
    rooms: AdminOverviewRooms
    files: AdminOverviewFiles
    sync: AdminOverviewSync
    books: AdminOverviewBooks
    recent_failures: List[AdminAuditEvidence]


class AdminSecurityCounts(BaseModel):
    inactive_users: int
    revoked_devices: int
    expired_devices: int
    admin_failed: int
    admin_rate_limited: int
    realtime_failed: int
    realtime_rate_limited: int


class AdminSecurityConfiguration(BaseModel):
    socket_auth_required: bool
    cors_credentials_enabled: bool
    cors_allowed_origin_count: int
    cors_wildcard_configured: bool


class AdminSecurityCapabilities(BaseModel):
    web_session_inventory_available: bool
    web_session_inventory_reason: str


class AdminSecurityResponse(BaseModel):
    generated_at: datetime
    counts: AdminSecurityCounts
    configuration: AdminSecurityConfiguration
    capabilities: AdminSecurityCapabilities
    admin_audit: List[AdminAuditEvidence]
    realtime_audit: List[RealtimeAuditEvidence]


class AgentConsoleStatus(BaseModel):
    server: dict
    backend: dict
    permissions: dict
