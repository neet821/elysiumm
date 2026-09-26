from __future__ import annotations


from typing import Literal
from schema_domains._base import Any, BaseModel, Field, List, Optional, datetime, field_validator, model_validator, urlparse

def validate_http_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("网址必须使用 HTTP 或 HTTPS")
    return normalized


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
