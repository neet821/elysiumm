from __future__ import annotations


from typing import Literal
from schema_domains._base import BaseModel, Field, List, Optional, datetime, field_validator, model_validator
from schema_domains.validation import _clean_optional_text, _validate_book_cover, _validate_book_tags, _validate_public_https_url, BOOK_READING_STATUSES

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
    is_featured: bool
    display_order: int
    last_read_at: Optional[datetime]


class BookAdminView(BookPublicView):
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
    books: List[BookPublicView]
    lists: List[BookListPublicView]
    recent: List[BookPublicView]


class BookCatalogAdminResponse(BaseModel):
    books: List[BookAdminView]
    lists: List[BookListAdminView]
