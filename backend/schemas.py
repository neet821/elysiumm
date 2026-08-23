from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Any, List, Literal, Optional
from datetime import datetime
from ipaddress import ip_address
from urllib.parse import urlparse

from input_validation import validate_new_password, validate_username


def validate_http_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("网址必须使用 HTTP 或 HTTPS")
    return normalized


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
    game_active: int


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


class AdminOverviewBackups(BaseModel):
    jobs: int
    latest_status: Optional[str] = None
    latest_created_at: Optional[datetime] = None


class AdminOverviewResponse(BaseModel):
    generated_at: datetime
    health: AdminOverviewHealth
    users: AdminOverviewUsers
    rooms: AdminOverviewRooms
    files: AdminOverviewFiles
    sync: AdminOverviewSync
    books: AdminOverviewBooks
    backups: AdminOverviewBackups
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


# Tag Schemas
class TagBase(BaseModel):
    name: str
    color: Optional[str] = "#3B82F6"

class TagCreate(TagBase):
    pass

class Tag(TagBase):
    id: int

    class Config:
        from_attributes = True

# Post Schemas
class PostBase(BaseModel):
    title: str
    content: Optional[str] = None
    category: Optional[str] = "未分类"  # 新增分类字段
    slug: Optional[str] = None
    pin_priority: int = 0
    is_hidden: bool = False

class PostCreate(PostBase):
    """创建文章的请求模型"""
    tags: List[str] = []

class PostUpdate(BaseModel):
    """更新文章的请求模型"""
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None  # 新增分类字段
    slug: Optional[str] = None
    pin_priority: Optional[int] = None
    is_hidden: Optional[bool] = None
    tags: Optional[List[str]] = None

class Post(PostBase):
    """文章响应模型"""
    id: int
    author_id: int
    views: int = 0  # 浏览次数
    created_at: datetime
    tags: List[Tag] = []

    class Config:
        from_attributes = True

class PostWithAuthor(Post):
    """带作者信息的文章模型"""
    author: Optional['UserSimple'] = None

    class Config:
        from_attributes = True

# User Schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

    @field_validator("username")
    @classmethod
    def validate_new_username(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("password")
    @classmethod
    def validate_registration_password(cls, value: str) -> str:
        return validate_new_password(value)

class UserUpdate(BaseModel):
    """用户信息更新"""
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("password")
    @classmethod
    def validate_optional_password(cls, value: Optional[str]) -> Optional[str]:
        return validate_new_password(value) if value is not None else None

class UserPasswordUpdate(BaseModel):
    """密码修改"""
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_replacement_password(cls, value: str) -> str:
        return validate_new_password(value)

class UserUsernameUpdate(BaseModel):
    """用户名修改"""
    new_username: str

    @field_validator("new_username")
    @classmethod
    def validate_replacement_username(cls, value: str) -> str:
        return validate_username(value)

class User(UserBase):
    id: int
    avatar: Optional[str] = None  # 🆕 头像URL
    role: str = "user"
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None
    posts: List[Post] = []

    class Config:
        from_attributes = True

class UserSimple(UserBase):
    """简化的用户信息(用于列表显示)"""
    id: int
    avatar: Optional[str] = None  # 🆕 头像URL
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# Token Schemas
class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    user: Optional[UserSimple] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenData(BaseModel):
    username: Optional[str] = None

class AgentConsoleStatus(BaseModel):
    server: dict
    backend: dict
    permissions: dict

class BackupFileInfo(BaseModel):
    id: int
    job_id: int
    type: str
    filename: str
    file_size: int
    sha256: str
    created_at: datetime

class BackupJobInfo(BaseModel):
    id: int
    type: str
    status: str
    created_by: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    summary: dict[str, Any] = {}
    files: List[BackupFileInfo] = []

class RestoreJobInfo(BaseModel):
    id: int
    backup_file_id: Optional[int] = None
    operation_id: str
    source_filename: Optional[str] = None
    status: str
    rollback_status: str = "not_attempted"
    created_by: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None

class FrpConfigUpdate(BaseModel):
    content: str

class FrpConfigRestoreRequest(BaseModel):
    backup_name: str

class FrpOperationInfo(BaseModel):
    id: int
    action: str
    status: str
    message: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True

# Link Category Schemas
class LinkCategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class LinkCategoryCreate(LinkCategoryBase):
    pass

class LinkCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class LinkCategory(LinkCategoryBase):
    id: int
    user_id: int
    created_at: datetime
    links: List['WebsiteLink'] = []

    class Config:
        from_attributes = True

# Website Link Schemas
class WebsiteLinkBase(BaseModel):
    title: str
    url: str
    description: Optional[str] = None
    category_id: int

class WebsiteLinkCreate(WebsiteLinkBase):
    pass

class WebsiteLinkUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None

class WebsiteLink(WebsiteLinkBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class BookmarkFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: Optional[int] = Field(default=None, gt=0)
    icon: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    is_sensitive: bool = False
    is_public: bool = False

    @model_validator(mode="after")
    def validate_visibility(self):
        if self.is_sensitive and self.is_public:
            raise ValueError("敏感文件夹不能设为公开")
        return self

class BookmarkFolderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    parent_id: Optional[int] = Field(default=None, gt=0)
    icon: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    is_sensitive: Optional[bool] = None
    is_public: Optional[bool] = None

    @model_validator(mode="after")
    def validate_visibility(self):
        if self.is_sensitive is True and self.is_public is True:
            raise ValueError("敏感文件夹不能设为公开")
        return self

class BookmarkFolderInfo(BaseModel):
    id: int
    user_id: int
    parent_id: Optional[int] = None
    name: str
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: int = 0
    is_sensitive: bool = False
    is_public: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BookmarkCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=1000)
    folder_id: Optional[int] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, max_length=4000)
    favicon: Optional[str] = Field(default=None, max_length=500)
    preview_url: Optional[str] = Field(default=None, max_length=1000)
    tags: List[str] = Field(default_factory=list, max_length=30)
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    is_public: bool = False
    is_pinned: bool = False
    show_description: bool = True
    show_preview: bool = True
    show_visit_count: bool = False
    allow_indexing: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_http_url(value)

    @field_validator("preview_url")
    @classmethod
    def validate_preview_url(cls, value: Optional[str]) -> Optional[str]:
        return validate_http_url(value) if value else value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: List[str]) -> List[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if any(len(value) > 50 for value in normalized):
            raise ValueError("收藏标签不能超过 50 个字符")
        if len(normalized) != len(set(normalized)):
            raise ValueError("收藏标签不能重复")
        return normalized

class BookmarkUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    url: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    folder_id: Optional[int] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, max_length=4000)
    favicon: Optional[str] = Field(default=None, max_length=500)
    preview_url: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[List[str]] = Field(default=None, max_length=30)
    sort_order: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    is_archived: Optional[bool] = None
    is_public: Optional[bool] = None
    is_pinned: Optional[bool] = None
    show_description: Optional[bool] = None
    show_preview: Optional[bool] = None
    show_visit_count: Optional[bool] = None
    allow_indexing: Optional[bool] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: Optional[str]) -> Optional[str]:
        return validate_http_url(value) if value else value

    @field_validator("preview_url")
    @classmethod
    def validate_preview_url(cls, value: Optional[str]) -> Optional[str]:
        return validate_http_url(value) if value else value

class BookmarkBulkAction(BaseModel):
    action: Literal["move", "copy", "delete", "archive", "sort"]
    ids: List[int] = Field(min_length=1, max_length=500)
    folder_id: Optional[int] = Field(default=None, gt=0)
    ordered_ids: Optional[List[int]] = Field(default=None, max_length=500)

    @field_validator("ids", "ordered_ids")
    @classmethod
    def validate_ids(cls, values: Optional[List[int]]) -> Optional[List[int]]:
        if values is None:
            return values
        if any(value <= 0 for value in values) or len(values) != len(set(values)):
            raise ValueError("收藏编号必须是互不重复的正整数")
        return values

class BookmarkBulkResult(BaseModel):
    matched: int
    requested: int
    created_ids: List[int] = Field(default_factory=list)


class PublicBookmarkFolder(BaseModel):
    id: int
    name: str
    icon: Optional[str] = None
    color: Optional[str] = None


class PublicBookmarkInfo(BaseModel):
    id: int
    title: str
    url: str
    description: Optional[str] = None
    favicon: Optional[str] = None
    preview_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    is_pinned: bool = False
    visit_count: Optional[int] = None
    allow_indexing: bool = False
    created_at: datetime
    last_visited_at: Optional[datetime] = None
    folder: Optional[PublicBookmarkFolder] = None


class PublicCollectionResponse(BaseModel):
    bookmarks: List[PublicBookmarkInfo] = Field(default_factory=list)
    folders: List[PublicBookmarkFolder] = Field(default_factory=list)


class BookmarkInfo(BaseModel):
    id: int
    user_id: int
    folder_id: Optional[int] = None
    title: str
    url: str
    description: Optional[str] = None
    favicon: Optional[str] = None
    preview_url: Optional[str] = None
    sort_order: int = 0
    is_archived: bool = False
    is_public: bool = False
    is_pinned: bool = False
    visit_count: int = 0
    show_description: bool = True
    show_preview: bool = True
    show_visit_count: bool = False
    allow_indexing: bool = False
    tags: List[str] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_visited_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BookmarkImportJobInfo(BaseModel):
    id: int
    user_id: int
    status: str
    source_type: str
    imported_count: int = 0
    folder_count: int = 0
    skipped_count: int = 0
    duplicate_count: int = 0
    dry_run: bool = False
    backup_id: Optional[int] = None
    report: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BookmarkBackupInfo(BaseModel):
    id: int
    filename: str
    file_size: int = 0
    sha256: Optional[str] = None
    created_at: datetime

class BookmarkRestoreRequest(BaseModel):
    replace_existing: bool = False


class SearchEngineCreate(BaseModel):
    category: str = Field(default="general", min_length=1, max_length=50)
    category_label: Optional[str] = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    url_template: str = Field(min_length=1, max_length=1000)
    icon: Optional[str] = Field(default=None, max_length=100)
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    is_enabled: bool = True

    @field_validator("url_template")
    @classmethod
    def validate_url_template(cls, value: str) -> str:
        if "{query}" not in value:
            raise ValueError("搜索引擎网址必须包含 {query}")
        return validate_http_url(value)


class SearchEngineUpdate(BaseModel):
    category: Optional[str] = Field(default=None, min_length=1, max_length=50)
    category_label: Optional[str] = Field(default=None, max_length=100)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    url_template: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    icon: Optional[str] = Field(default=None, max_length=100)
    sort_order: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    is_enabled: Optional[bool] = None

    @field_validator("url_template")
    @classmethod
    def validate_url_template(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if "{query}" not in value:
            raise ValueError("搜索引擎网址必须包含 {query}")
        return validate_http_url(value)


class SearchEngineInfo(SearchEngineCreate):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Photo Schemas
class PhotoBase(BaseModel):
    url: str
    caption: Optional[str] = None
    location: Optional[str] = None
    is_featured: bool = False

class PhotoCreate(PhotoBase):
    tags: List[str] = []

class PhotoUpdate(BaseModel):
    url: Optional[str] = None
    caption: Optional[str] = None
    location: Optional[str] = None
    is_featured: Optional[bool] = None
    tags: Optional[List[str]] = None

class Photo(PhotoBase):
    id: int
    created_at: datetime
    tags: List[Tag] = []

    class Config:
        from_attributes = True


class ArchiveItem(BaseModel):
    id: str
    source_id: int
    type: Literal["writing", "article", "essay", "photo", "book", "album", "movie", "game"]
    content_type: Optional[Literal["article", "essay"]] = None
    title: str
    excerpt: Optional[str] = None
    href: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    author_name: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime


class ArchiveResponse(BaseModel):
    items: List[ArchiveItem] = Field(default_factory=list)
    total: int
    skip: int
    limit: int


# Homepage Schemas
class HomepageCardConfig(BaseModel):
    id: Literal[
        "index",
        "writing",
        "photography",
        "collection",
        "messages",
        "history",
        "quote",
        "status",
    ]
    size: Literal["small", "medium", "wide"]
    theme: Literal["archive", "paper", "film", "note", "midnight"]


class HomepageSceneConfig(BaseModel):
    model_config = {"extra": "forbid"}

    id: Literal["study", "darkroom", "listening", "lounge"]
    label: str = Field(min_length=1, max_length=40)
    featured_post_ids: List[int] = Field(default_factory=list, max_length=8)
    featured_photo_ids: List[int] = Field(default_factory=list, max_length=8)
    featured_book_ids: List[int] = Field(default_factory=list, max_length=8)
    featured_movie_ids: List[int] = Field(default_factory=list, max_length=8)
    featured_album_ids: List[int] = Field(default_factory=list, max_length=8)

    @field_validator(
        "featured_post_ids",
        "featured_photo_ids",
        "featured_book_ids",
        "featured_movie_ids",
        "featured_album_ids",
    )
    @classmethod
    def validate_scene_ids(cls, values: List[int]) -> List[int]:
        if any(value <= 0 for value in values) or len(values) != len(set(values)):
            raise ValueError("场景内容编号必须是互不重复的正整数")
        return values


def _default_homepage_scenes() -> List[dict[str, Any]]:
    return [
        {"id": "study", "label": "书房"},
        {"id": "darkroom", "label": "暗房"},
        {"id": "listening", "label": "唱片室"},
        {"id": "lounge", "label": "会客厅"},
    ]


class HomepageConfig(BaseModel):
    version: Literal[2] = 2
    hero_prefix: str = Field(min_length=1, max_length=80)
    hero_title: str = Field(min_length=1, max_length=120)
    german_line: str = Field(min_length=1, max_length=240)
    introduction: str = Field(min_length=1, max_length=1200)
    short_quote: str = Field(default="", max_length=300)
    featured_post_ids: List[int] = Field(default_factory=list, max_length=12)
    featured_photo_ids: List[int] = Field(default_factory=list, max_length=12)
    featured_collection_ids: List[int] = Field(default_factory=list, max_length=12)
    featured_track_ids: List[int] = Field(default_factory=list, max_length=5)
    show_messages: bool = True
    show_history: bool = True
    background_mode: Literal["auto", "paper", "midnight"] = "auto"
    cards: List[HomepageCardConfig] = Field(min_length=1, max_length=12)
    scenes: List[HomepageSceneConfig] = Field(
        default_factory=lambda: [
            HomepageSceneConfig.model_validate(item)
            for item in _default_homepage_scenes()
        ],
        min_length=4,
        max_length=4,
    )

    @field_validator(
        "featured_post_ids",
        "featured_photo_ids",
        "featured_collection_ids",
        "featured_track_ids",
    )
    @classmethod
    def validate_positive_unique_ids(cls, values: List[int]) -> List[int]:
        if any(value <= 0 for value in values):
            raise ValueError("内容编号必须是正整数")
        if len(values) != len(set(values)):
            raise ValueError("内容编号不能重复")
        return values

    @model_validator(mode="after")
    def validate_unique_cards(self):
        identifiers = [card.id for card in self.cards]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("首页卡片不能重复")
        scene_ids = [scene.id for scene in self.scenes]
        expected = ["study", "darkroom", "listening", "lounge"]
        if scene_ids != expected:
            raise ValueError("首页场景必须按书房、暗房、唱片室、会客厅排列且各出现一次")
        return self


class HomepageSettingsView(HomepageConfig):
    revision: int = 0
    updated_at: Optional[datetime] = None


class HomepageSettingsUpdate(BaseModel):
    revision: int = Field(ge=0)
    settings: HomepageConfig


class HomepagePublicResponse(BaseModel):
    settings: HomepageSettingsView
    posts: List[PostWithAuthor] = Field(default_factory=list)
    photos: List[Photo] = Field(default_factory=list)
    messages: List["MessageBoardResponse"] = Field(default_factory=list)
    collections: List[Any] = Field(default_factory=list)
    scenes: List[Any] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    player_tracks: List[dict[str, Any]] = Field(default_factory=list)

# Sync Room Schemas
class SyncRoomBase(BaseModel):
    room_name: str
    mode: str = "url"  # url=外链, upload=上传, local=本地同步
    video_source: Optional[str] = None
    control_mode: str = "host_only"
    password: Optional[str] = None # 接收明文密码
    type: str = "video" # 'video' or 'game'
    game_type: Optional[str] = None # e.g. 'gomoku'

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
    game_type: Optional[str] = None
    game_state: Optional[str] = None
    is_active: bool
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
    game_type: Optional[str] = None
    game_state: Optional[str] = None
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

# WebSocket 事件消息
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

# Resource Request Schemas
class ResourceRequestBase(BaseModel):
    title: str
    content: str
    is_anonymous: bool = False
    is_private: bool = False

class ResourceRequestCreate(ResourceRequestBase):
    pass

class WishlistReplyBase(BaseModel):
    content: str

class WishlistReplyCreate(WishlistReplyBase):
    pass

class WishlistReply(WishlistReplyBase):
    id: int
    request_id: int
    user_id: int
    created_at: datetime
    user: Optional[UserSimple] = None

    class Config:
        from_attributes = True

class ResourceRequestUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    reply_content: Optional[str] = None
    file_url: Optional[str] = None
    external_link: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_anonymous: Optional[bool] = None
    is_private: Optional[bool] = None

class ResourceRequest(ResourceRequestBase):
    id: int
    user_id: int
    status: str
    reply_content: Optional[str] = None
    file_url: Optional[str] = None
    external_link: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    user: Optional[UserSimple] = None
    replies: List[WishlistReply] = []

    class Config:
        from_attributes = True

class KickMemberRequest(BaseModel):
    """踢出成员请求"""
    target_user_id: int


class GameRoomSettings(BaseModel):
    model_config = {"extra": "forbid"}

    turn_timeout_seconds: int = Field(default=90, ge=15, le=300)


class GameRoomCreate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(default="井字棋房间", min_length=1, max_length=80)
    game_slug: str = Field(default="tic-tac-toe", min_length=1, max_length=80)
    visibility: Literal["public", "private"] = "public"
    password: Optional[str] = Field(default=None, min_length=4, max_length=72)
    allow_spectators: bool = True
    settings: GameRoomSettings = Field(default_factory=GameRoomSettings)


class GameRoomJoin(BaseModel):
    model_config = {"extra": "forbid"}

    role: Literal["player", "spectator"] = "player"
    password: Optional[str] = Field(default=None, max_length=72)
    invite_token: Optional[str] = Field(default=None, max_length=64)


class GameRoomReady(BaseModel):
    model_config = {"extra": "forbid"}

    ready: bool
    expected_room_version: int = Field(ge=0)


class GameRoomRevision(BaseModel):
    model_config = {"extra": "forbid"}

    expected_room_version: int = Field(ge=0)


class GameRoomInviteCreate(BaseModel):
    model_config = {"extra": "forbid"}

    ttl_minutes: int = Field(default=60, ge=1, le=1440)


class GameActionRequest(BaseModel):
    model_config = {"extra": "forbid"}

    expected_version: int = Field(ge=0)
    action: dict[str, Any]

class MessageBoardBase(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    parent_id: Optional[int] = Field(default=None, gt=0)

class MessageBoardCreate(MessageBoardBase):
    pass

class MessageBoardResponse(MessageBoardBase):
    id: int
    user_id: int
    likes: int = 0
    created_at: datetime
    user: Optional['UserSimple'] = None
    replies: List['MessageBoardResponse'] = []

    class Config:
        from_attributes = True


BOOK_READING_STATUSES = {"unread", "reading", "paused", "completed"}


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_book_cover(value: Optional[str]) -> Optional[str]:
    normalized = _clean_optional_text(value)
    if normalized is None:
        return None
    if normalized.startswith("/") and not normalized.startswith("//"):
        if (
            ".." not in normalized.split("/")
            and "\\" not in normalized
            and "?" not in normalized
            and "#" not in normalized
            and not any(ord(character) < 32 for character in normalized)
        ):
            return normalized
        raise ValueError("封面路径必须位于应用内部")
    parsed = urlparse(normalized)
    if (
        parsed.scheme == "https"
        and parsed.netloc
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    ):
        return normalized
    raise ValueError("封面网址必须使用 HTTPS 或应用内相对路径")


def _validate_reader_path(value: Optional[str]) -> Optional[str]:
    normalized = _clean_optional_text(value)
    if normalized is None:
        return None
    if (
        normalized.startswith("/")
        or "\\" in normalized
        or "?" in normalized
        or "#" in normalized
        or ":" in normalized
        or ".." in normalized.split("/")
        or any(not part for part in normalized.split("/"))
    ):
        raise ValueError("阅读路径必须是安全的 Kavita 相对路径")
    return normalized


def _validate_book_tags(value: List[str]) -> List[str]:
    if len(value) > 12:
        raise ValueError("最多允许 12 个标签")
    normalized: List[str] = []
    seen = set()
    for tag in value:
        clean = tag.strip()
        if not clean or len(clean) > 40:
            raise ValueError("每个标签必须包含 1 到 40 个字符")
        key = clean.casefold()
        if key in seen:
            raise ValueError("标签不能重复")
        seen.add(key)
        normalized.append(clean)
    return normalized


def _validate_public_https_url(value: Optional[str]) -> Optional[str]:
    normalized = _clean_optional_text(value)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("外链必须是无凭据的 HTTPS 网址")
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("外链不能指向本机或内网")
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("外链不能指向本机或内网")
    return normalized


MEDIA_STATUSES = {
    "planned",
    "in_progress",
    "paused",
    "completed",
    "dropped",
    "wishlist",
}
MEDIA_METADATA_FIELDS = {
    "title",
    "creator",
    "cover_url",
    "year",
    "summary",
    "tags",
    "source",
    "source_id",
    "external_url",
    "metadata",
}


class MediaCreate(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["book", "movie", "album", "game"]
    slug: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    title: str = Field(min_length=1, max_length=255)
    creator: Optional[str] = Field(default=None, max_length=255)
    cover_url: Optional[str] = Field(default=None, max_length=700)
    year: Optional[int] = Field(default=None, ge=1000, le=2200)
    summary: Optional[str] = Field(default=None, max_length=12_000)
    tags: List[str] = Field(default_factory=list, max_length=12)
    status: Literal[
        "planned", "in_progress", "paused", "completed", "dropped", "wishlist"
    ] = "planned"
    activity_at: Optional[datetime] = None
    personal_rating: Optional[float] = Field(default=None, ge=0, le=10)
    personal_notes: Optional[str] = Field(default=None, max_length=20_000)
    is_public: bool = False
    is_featured: bool = False
    source: str = Field(default="manual", min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    source_id: Optional[str] = Field(default=None, max_length=255)
    external_url: Optional[str] = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def require_media_title(cls, value: str) -> str:
        normalized = _clean_optional_text(value)
        if normalized is None:
            raise ValueError("标题不能为空")
        return normalized

    @field_validator("creator", "summary", "personal_notes", "source_id")
    @classmethod
    def clean_media_text(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value)

    @field_validator("cover_url")
    @classmethod
    def validate_media_cover(cls, value: Optional[str]) -> Optional[str]:
        return _validate_book_cover(value)

    @field_validator("external_url")
    @classmethod
    def validate_media_external_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_public_https_url(value)

    @field_validator("tags")
    @classmethod
    def validate_media_tags(cls, value: List[str]) -> List[str]:
        return _validate_book_tags(value)


class MediaPatch(BaseModel):
    model_config = {"extra": "forbid"}

    revision: int = Field(ge=0)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    creator: Optional[str] = Field(default=None, max_length=255)
    cover_url: Optional[str] = Field(default=None, max_length=700)
    year: Optional[int] = Field(default=None, ge=1000, le=2200)
    summary: Optional[str] = Field(default=None, max_length=12_000)
    tags: Optional[List[str]] = Field(default=None, max_length=12)
    status: Optional[Literal[
        "planned", "in_progress", "paused", "completed", "dropped", "wishlist"
    ]] = None
    activity_at: Optional[datetime] = None
    personal_rating: Optional[float] = Field(default=None, ge=0, le=10)
    personal_notes: Optional[str] = Field(default=None, max_length=20_000)
    is_public: Optional[bool] = None
    is_featured: Optional[bool] = None
    source: Optional[str] = Field(default=None, min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    source_id: Optional[str] = Field(default=None, max_length=255)
    external_url: Optional[str] = Field(default=None, max_length=1000)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("title", "creator", "summary", "personal_notes", "source_id")
    @classmethod
    def clean_patch_text(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value)

    @field_validator("cover_url")
    @classmethod
    def validate_patch_cover(cls, value: Optional[str]) -> Optional[str]:
        return _validate_book_cover(value)

    @field_validator("external_url")
    @classmethod
    def validate_patch_external_url(cls, value: Optional[str]) -> Optional[str]:
        return _validate_public_https_url(value)

    @field_validator("tags")
    @classmethod
    def validate_patch_tags(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _validate_book_tags(value) if value is not None else None

    @model_validator(mode="after")
    def validate_patch_intent(self):
        direct_fields = self.model_fields_set - {"revision"}
        if not direct_fields:
            raise ValueError("没有可更新的字段")
        return self


class MediaEntryView(BaseModel):
    id: int
    kind: Literal["book", "movie", "album", "game"]
    title: str
    creator: Optional[str] = None
    cover_url: Optional[str] = None
    year: Optional[int] = None
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    status: str
    activity_at: Optional[datetime] = None
    personal_rating: Optional[float] = None
    personal_notes: Optional[str] = None
    source: str
    source_id: Optional[str] = None
    safe_external_url: Optional[str] = None


class MediaEntryAdminView(MediaEntryView):
    is_public: bool
    is_featured: bool
    revision: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    metadata_overrides: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MediaMutationResult(BaseModel):
    entry: MediaEntryAdminView
    diff: List[dict[str, Any]] = Field(default_factory=list)
    applied: bool


class MediaRecentResponse(BaseModel):
    items: List[MediaEntryView] = Field(default_factory=list)


class BookCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=255)
    author: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    cover_url: Optional[str] = Field(default=None, max_length=500)
    category: Optional[str] = Field(default=None, max_length=80)
    tags: List[str] = Field(default_factory=list)
    reading_status: Literal["unread", "reading", "paused", "completed"] = "unread"
    source: str = Field(default="manual", min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    source_id: Optional[str] = Field(default=None, max_length=255)
    isbn: Optional[str] = Field(default=None, max_length=32)
    publication_year: Optional[int] = Field(default=None, ge=1000, le=2200)
    personal_rating: Optional[float] = Field(default=None, ge=0, le=10)
    personal_notes: Optional[str] = Field(default=None, max_length=20_000)
    reader_path: Optional[str] = Field(default=None, max_length=1000)
    is_public: bool = False
    is_featured: bool = False
    display_order: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        normalized = _clean_optional_text(value)
        if normalized is None:
            raise ValueError("标题不能为空")
        return normalized

    @field_validator("author", "description", "category", "source_id", "isbn", "personal_notes")
    @classmethod
    def clean_text(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value)

    @field_validator("cover_url")
    @classmethod
    def validate_cover(cls, value: Optional[str]) -> Optional[str]:
        return _validate_book_cover(value)

    @field_validator("reader_path")
    @classmethod
    def validate_reader(cls, value: Optional[str]) -> Optional[str]:
        return _validate_reader_path(value)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: List[str]) -> List[str]:
        return _validate_book_tags(value)


class BookUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    revision: int = Field(ge=0)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    author: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    cover_url: Optional[str] = Field(default=None, max_length=500)
    category: Optional[str] = Field(default=None, max_length=80)
    tags: Optional[List[str]] = None
    reading_status: Optional[Literal["unread", "reading", "paused", "completed"]] = None
    source: Optional[str] = Field(default=None, min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    source_id: Optional[str] = Field(default=None, max_length=255)
    isbn: Optional[str] = Field(default=None, max_length=32)
    publication_year: Optional[int] = Field(default=None, ge=1000, le=2200)
    personal_rating: Optional[float] = Field(default=None, ge=0, le=10)
    personal_notes: Optional[str] = Field(default=None, max_length=20_000)
    reader_path: Optional[str] = Field(default=None, max_length=1000)
    is_public: Optional[bool] = None
    is_featured: Optional[bool] = None
    display_order: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    last_read_at: Optional[datetime] = None

    @field_validator("title", "author", "description", "category", "source_id", "isbn", "personal_notes")
    @classmethod
    def clean_text(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value)

    @field_validator("cover_url")
    @classmethod
    def validate_cover(cls, value: Optional[str]) -> Optional[str]:
        return _validate_book_cover(value)

    @field_validator("reader_path")
    @classmethod
    def validate_reader(cls, value: Optional[str]) -> Optional[str]:
        return _validate_reader_path(value)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _validate_book_tags(value) if value is not None else None

    @model_validator(mode="after")
    def reject_null_required_updates(self):
        required = {
            "slug",
            "title",
            "reading_status",
            "is_public",
            "is_featured",
            "display_order",
        }
        for field in required.intersection(self.model_fields_set):
            if getattr(self, field) is None:
                raise ValueError("字段不能为 null")
        return self


class BookPublicView(BaseModel):
    id: int
    slug: str
    title: str
    author: Optional[str]
    description: Optional[str]
    cover_url: Optional[str]
    category: Optional[str]
    tags: List[str]
    reading_status: str
    source: str = "manual"
    source_id: Optional[str] = None
    isbn: Optional[str] = None
    publication_year: Optional[int] = None
    personal_rating: Optional[float] = None
    personal_notes: Optional[str] = None
    reader_url: Optional[str]
    is_featured: bool
    display_order: int
    last_read_at: Optional[datetime]


class BookAdminView(BookPublicView):
    reader_path: Optional[str]
    is_public: bool
    revision: int
    metadata_overrides: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BookListCreate(BaseModel):
    model_config = {"extra": "forbid"}

    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    is_public: bool = False
    display_order: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        normalized = _clean_optional_text(value)
        if normalized is None:
            raise ValueError("标题不能为空")
        return normalized

    @field_validator("description")
    @classmethod
    def clean_text(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value)


class BookListUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    revision: int = Field(ge=0)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    is_public: Optional[bool] = None
    display_order: Optional[int] = Field(default=None, ge=0, le=1_000_000)

    @field_validator("title", "description")
    @classmethod
    def clean_text(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_text(value)

    @model_validator(mode="after")
    def reject_null_required_updates(self):
        for field in {"slug", "title", "is_public", "display_order"}.intersection(
            self.model_fields_set
        ):
            if getattr(self, field) is None:
                raise ValueError("字段不能为 null")
        return self


class BookListItemsUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    revision: int = Field(ge=0)
    book_ids: List[int] = Field(max_length=100)

    @field_validator("book_ids")
    @classmethod
    def validate_book_ids(cls, value: List[int]) -> List[int]:
        if any(book_id <= 0 for book_id in value) or len(set(value)) != len(value):
            raise ValueError("书籍编号必须是互不重复的正整数")
        return value


class BookListPublicView(BaseModel):
    id: int
    slug: str
    title: str
    description: Optional[str]
    display_order: int
    books: List[BookPublicView]


class BookListAdminView(BookListPublicView):
    is_public: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class BookCatalogPublicResponse(BaseModel):
    reader_available: bool
    books: List[BookPublicView]
    lists: List[BookListPublicView]
    recent: List[BookPublicView]


class BookCatalogAdminResponse(BaseModel):
    reader_available: bool
    books: List[BookAdminView]
    lists: List[BookListAdminView]

# 更新前向引用
SyncRoomInfo.model_rebuild()
MessageBoardResponse.model_rebuild()
HomepagePublicResponse.model_rebuild()
