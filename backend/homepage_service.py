"""Validated homepage settings and public homepage content assembly."""

from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy.orm import Session, joinedload

import bookmark_service
import crud
import models
import schemas
from admin_audit import add_admin_audit


DEFAULT_HOMEPAGE_CONFIG = {
    "hero_prefix": "Hello, this is",
    "hero_title": "Blue Album.",
    "german_line": "Wovon man nicht sprechen kann, darüber muss man schweigen.",
    "introduction": "文字、照片与沿途收藏，都留在这本私人相册里。",
    "short_quote": "把安静的部分留下来。",
    "featured_post_ids": [],
    "featured_photo_ids": [],
    "featured_collection_ids": [],
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

    return {
        "settings": settings,
        "posts": posts,
        "photos": photos,
        "messages": messages,
        "collections": [
            bookmark_service.serialize_public_bookmark(bookmark)
            for bookmark in collection_items
        ],
    }
