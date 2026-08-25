"""Validated homepage settings and public homepage content assembly."""

from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy.orm import Session, joinedload

import bookmark_service
import book_service
import crud
import media_service
import models
import schemas
from admin_audit import add_admin_audit
from config import config


DEFAULT_HOMEPAGE_CONFIG = {
    "version": 2,
    "hero_prefix": "Hello, this is",
    "article_title_scale": 0.8,
    "hero_title": "Blue Album.",
    "german_line": "Wovon man nicht sprechen kann, darüber muss man schweigen.",
    "introduction": "文字、照片与沿途收藏，都留在这本私人相册里。",
    "short_quote": "把安静的部分留下来。",
    "featured_post_ids": [],
    "featured_photo_ids": [],
    "featured_collection_ids": [],
    "featured_track_ids": [],
    "show_messages": True,
    "show_history": True,
    "background_mode": "auto",
    "cards": [
        {"id": "index", "size": "small", "theme": "archive"},
        {"id": "writing", "size": "wide", "theme": "paper"},
        {"id": "photography", "size": "medium", "theme": "film"},
        {"id": "collection", "size": "medium", "theme": "archive"},
        {"id": "messages", "size": "medium", "theme": "note"},
        {"id": "history", "size": "medium", "theme": "archive"},
        {"id": "quote", "size": "small", "theme": "paper"},
    ],
    "scenes": [
        {"id": "study", "label": "书房"},
        {"id": "darkroom", "label": "暗房"},
        {"id": "listening", "label": "唱片室"},
        {"id": "lounge", "label": "会客厅"},
    ],
}


class HomepageRevisionConflict(RuntimeError):
    pass


def default_config() -> schemas.HomepageConfig:
    return schemas.HomepageConfig.model_validate(DEFAULT_HOMEPAGE_CONFIG)


def load_homepage_settings(db: Session) -> schemas.HomepageSettingsView:
    row = db.query(models.HomepageSetting).filter(models.HomepageSetting.id == 1).first()
    if row is None:
        return schemas.HomepageSettingsView(
            **default_config().model_dump(mode="json"),
            revision=0,
            updated_at=None,
        )

    try:
        config = schemas.HomepageConfig.model_validate(json.loads(row.config_json))
    except (json.JSONDecodeError, ValueError, TypeError):
        config = default_config()
    return schemas.HomepageSettingsView(
        **config.model_dump(mode="json"),
        revision=row.revision,
        updated_at=row.updated_at,
    )


def save_homepage_settings(
    db: Session,
    payload: schemas.HomepageSettingsUpdate,
    *,
    actor_id: int,
) -> schemas.HomepageSettingsView:
    row = (
        db.query(models.HomepageSetting)
        .filter(models.HomepageSetting.id == 1)
        .with_for_update()
        .first()
    )
    current_revision = row.revision if row is not None else 0
    if payload.revision != current_revision:
        raise HomepageRevisionConflict(
            f"homepage settings changed from revision {payload.revision} to {current_revision}"
        )

    next_revision = current_revision + 1
    config = payload.settings.model_dump(mode="json")
    serialized = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    now = datetime.utcnow()
    if row is None:
        row = models.HomepageSetting(
            id=1,
            config_json=serialized,
            revision=next_revision,
            updated_by=actor_id,
            updated_at=now,
        )
        db.add(row)
    else:
        row.config_json = serialized
        row.revision = next_revision
        row.updated_by = actor_id
        row.updated_at = now

    add_admin_audit(
        db,
        actor_id=actor_id,
        action="homepage_settings_update",
        resource_type="homepage_settings",
        resource_id=1,
        detail=(
            f"revision={next_revision} cards={len(config['cards'])} "
            f"posts={len(config['featured_post_ids'])} "
            f"photos={len(config['featured_photo_ids'])} "
            f"messages={'on' if config['show_messages'] else 'off'}"
        ),
    )
    db.commit()
    db.refresh(row)
    return schemas.HomepageSettingsView(
        **payload.settings.model_dump(mode="json"),
        revision=row.revision,
        updated_at=row.updated_at,
    )


def _ordered_selected(items, identifiers):
    if not identifiers:
        return items
    by_id = {item.id: item for item in items}
    return [by_id[item_id] for item_id in identifiers if item_id in by_id]


def _public_posts(db: Session, identifiers: list[int], *, limit: int = 4):
    query = (
        db.query(models.Post)
        .options(joinedload(models.Post.author), joinedload(models.Post.tags))
        .filter(models.Post.is_hidden.is_(False))
    )
    if identifiers:
        query = query.filter(models.Post.id.in_(identifiers))
    rows = query.order_by(
        models.Post.pin_priority.desc(),
        models.Post.created_at.desc(),
    ).limit(limit).all()
    return _ordered_selected(rows, identifiers)


def _public_photos(db: Session, identifiers: list[int], *, limit: int = 4):
    query = db.query(models.Photo).options(joinedload(models.Photo.tags))
    if identifiers:
        query = query.filter(models.Photo.id.in_(identifiers))
    else:
        query = query.filter(models.Photo.is_featured.is_(True))
    rows = query.order_by(models.Photo.created_at.desc()).limit(limit).all()
    return _ordered_selected(rows, identifiers)


def _safe_capability_url(value: str | None) -> str | None:
    try:
        return schemas._validate_public_https_url(value)
    except ValueError:
        return None


def _homepage_capabilities() -> dict:
    raindrop_url = _safe_capability_url(config.RAINDROP_PUBLIC_URL)
    kavita_url = book_service._validated_base_url(config.KAVITA_PUBLIC_BASE_URL)
    return {
        "raindrop": {
            "configured": raindrop_url is not None,
            "url": raindrop_url,
        },
        "kavita": {
            "configured": kavita_url is not None,
            "url": kavita_url,
        },
        "records": {"mode": "manual", "message": "记录由 Obsidian 手动维护"},
    }


def _scene_payloads(
    db: Session,
    settings: schemas.HomepageSettingsView,
    *,
    fallback_posts,
    fallback_photos,
    fallback_messages,
) -> list[dict]:
    capabilities = _homepage_capabilities()
    scenes: list[dict] = []
    for scene in settings.scenes:
        base = {
            "id": scene.id,
            "label": scene.label,
            "posts": [],
            "photos": [],
            "media": [],
            "messages": [],
            "links": [],
        }
        if scene.id == "study":
            base["posts"] = (
                _public_posts(db, scene.featured_post_ids)
                if scene.featured_post_ids
                else fallback_posts
            )
            base["media"] = media_service.selected_public(
                db,
                "book",
                scene.featured_book_ids,
                limit=4,
            )
            if capabilities["kavita"]["configured"]:
                base["links"].append(
                    {"id": "kavita", "label": "Kavita", "url": capabilities["kavita"]["url"]}
                )
            if capabilities["raindrop"]["configured"]:
                base["links"].append(
                    {"id": "raindrop", "label": "Raindrop", "url": capabilities["raindrop"]["url"]}
                )
        elif scene.id == "darkroom":
            base["photos"] = (
                _public_photos(db, scene.featured_photo_ids)
                if scene.featured_photo_ids
                else fallback_photos
            )
            base["media"] = media_service.selected_public(
                db,
                "movie",
                scene.featured_movie_ids,
                limit=4,
            )
        elif scene.id == "listening":
            base["media"] = media_service.selected_public(
                db,
                "album",
                scene.featured_album_ids,
                limit=4,
            )
            base["links"] = [{"id": "music-room", "label": "听歌房", "url": "/music"}]
        elif scene.id == "lounge":
            base["messages"] = fallback_messages
            base["links"] = [
                {"id": "messages", "label": "留言板", "url": "/messages"},
                {"id": "live", "label": "直播", "url": "/live"},
            ]
        scenes.append(base)
    return scenes


def public_homepage(db: Session) -> dict:
    settings = load_homepage_settings(db)

    post_query = (
        db.query(models.Post)
        .options(joinedload(models.Post.author), joinedload(models.Post.tags))
        .filter(models.Post.is_hidden.is_(False))
    )
    if settings.featured_post_ids:
        post_query = post_query.filter(models.Post.id.in_(settings.featured_post_ids))
    posts = post_query.order_by(
        models.Post.pin_priority.desc(),
        models.Post.created_at.desc(),
    ).limit(4).all()
    posts = _ordered_selected(posts, settings.featured_post_ids)

    photo_query = (
        db.query(models.Photo)
        .options(joinedload(models.Photo.tags))
        .filter(models.Photo.is_featured.is_(True))
    )
    if settings.featured_photo_ids:
        photo_query = photo_query.filter(models.Photo.id.in_(settings.featured_photo_ids))
    photos = photo_query.order_by(models.Photo.created_at.desc()).limit(4).all()
    photos = _ordered_selected(photos, settings.featured_photo_ids)

    messages = (
        crud.get_message_board_entries(db, skip=0, limit=3)
        if settings.show_messages
        else []
    )
    collection_items = bookmark_service.public_bookmarks(
        db,
        bookmark_ids=(
            settings.featured_collection_ids
            if settings.featured_collection_ids
            else None
        ),
        limit=4,
    )
    player_tracks = []
    if settings.featured_track_ids:
        tracks = db.query(models.CanonicalTrack).filter(models.CanonicalTrack.id.in_(settings.featured_track_ids)).all()
        by_id = {track.id: track for track in tracks}
        player_tracks = [
            {
                "id": track.id,
                "title": track.title,
                "artist": track.primary_artist,
                "album": track.album,
                "cover_url": track.artwork_url,
                "audio_url": f"/api/music/tracks/{track.id}/audio",
            }
            for track_id in settings.featured_track_ids
            if (track := by_id.get(track_id))
        ]

    capabilities = _homepage_capabilities()
    scenes = _scene_payloads(
        db,
        settings,
        fallback_posts=posts,
        fallback_photos=photos,
        fallback_messages=messages,
    )
    # Scenes are retained for the existing room/homepage clients, but the
    # public response must contain plain data rather than ORM objects because
    # these fields are intentionally schema-agnostic.
    for scene in scenes:
        scene["posts"] = [
            schemas.PostWithAuthor.model_validate(post).model_dump(mode="json")
            for post in scene.get("posts", [])
        ]
        scene["photos"] = [
            schemas.Photo.model_validate(photo).model_dump(mode="json")
            for photo in scene.get("photos", [])
        ]
        scene["messages"] = [
            schemas.MessageBoardResponse.model_validate(message).model_dump(mode="json")
            for message in scene.get("messages", [])
        ]

    return {
        "settings": settings,
        "posts": posts,
        "photos": photos,
        "messages": messages,
        "collections": [
            bookmark_service.serialize_public_bookmark(bookmark)
            for bookmark in collection_items
        ],
        "scenes": scenes,
        "capabilities": capabilities,
        "player_tracks": player_tracks,
    }
