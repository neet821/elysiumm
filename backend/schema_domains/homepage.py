from __future__ import annotations


from typing import Literal
from schema_domains._base import Any, BaseModel, Field, List, Optional, datetime, field_validator, model_validator
from schema_domains.content import Photo, PostWithAuthor

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
    article_title_scale: float = Field(default=0.8, ge=0.6, le=1.2)
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
    messages: List["MessageBoardResponse"] = Field(default_factory=list)  # noqa: F821 - rebuilt by schemas.py facade
    collections: List[Any] = Field(default_factory=list)
    scenes: List[Any] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    player_tracks: List[dict[str, Any]] = Field(default_factory=list)
