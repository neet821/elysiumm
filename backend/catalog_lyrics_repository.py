"""Persistence helpers for cached provider lyrics."""

from __future__ import annotations

from sqlalchemy.orm import Session

import models
from catalog_domain import PROVIDER_ORDER


def cached_lyrics(
    db: Session,
    canonical_id: int,
    language: str,
    now,
) -> models.TrackLyrics | None:
    rows = (
        db.query(models.TrackLyrics)
        .filter(
            models.TrackLyrics.canonical_track_id == canonical_id,
            models.TrackLyrics.language == language,
        )
        .all()
    )
    valid = [row for row in rows if row.expires_at is None or row.expires_at > now]
    valid.sort(key=lambda row: (PROVIDER_ORDER.get(row.provider, 100), row.id))
    return valid[0] if valid else None


def upsert_lyrics(
    db: Session,
    *,
    canonical_id: int,
    provider_mapping_id: int,
    provider: str,
    language: str,
    timed_text: str,
    translation_text: str | None,
    fetched_at,
    expires_at,
) -> models.TrackLyrics:
    row = (
        db.query(models.TrackLyrics)
        .filter(
            models.TrackLyrics.canonical_track_id == canonical_id,
            models.TrackLyrics.provider == provider,
            models.TrackLyrics.language == language,
        )
        .one_or_none()
    )
    if row is None:
        row = models.TrackLyrics(
            canonical_track_id=canonical_id,
            provider=provider,
            language=language,
        )
        db.add(row)
    row.provider_mapping_id = provider_mapping_id
    row.timed_text = timed_text
    row.translation_text = translation_text
    row.fetched_at = fetched_at
    row.expires_at = expires_at
    db.flush()
    return row
