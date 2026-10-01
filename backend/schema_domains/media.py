from __future__ import annotations


from typing import Literal
from schema_domains._base import Any, BaseModel, Field, List, Optional, datetime, field_validator, model_validator
from schema_domains.validation import _clean_optional_text, _validate_book_cover, _validate_book_tags, _validate_public_https_url, MEDIA_STATUSES, MEDIA_METADATA_FIELDS

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
