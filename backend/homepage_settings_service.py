"""Read and update validated homepage settings."""

from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy.orm import Session

import models
import schemas
from admin_audit import add_admin_audit


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
