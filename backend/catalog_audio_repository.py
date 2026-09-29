"""Persistence helpers for resolved catalog audio sources."""

from __future__ import annotations

from sqlalchemy.orm import Session

import models


def audio_sources_for_track(
    db: Session,
    canonical_id: int,
) -> list[models.TrackAudioSource]:
    return (
        db.query(models.TrackAudioSource)
        .filter(models.TrackAudioSource.canonical_track_id == canonical_id)
        .all()
    )


def upsert_audio_source(
    db: Session,
    *,
    canonical_id: int,
    provider_mapping_id: int | None,
    source_type: str,
    playback_url: str,
    availability: str,
    expires_at,
) -> models.TrackAudioSource:
    source = (
        db.query(models.TrackAudioSource)
        .filter(
            models.TrackAudioSource.canonical_track_id == canonical_id,
            models.TrackAudioSource.provider_mapping_id == provider_mapping_id,
            models.TrackAudioSource.source_type == source_type,
        )
        .one_or_none()
    )
    if source is None:
        source = models.TrackAudioSource(
            canonical_track_id=canonical_id,
            provider_mapping_id=provider_mapping_id,
            source_type=source_type,
        )
        db.add(source)
    source.playback_url = playback_url
    source.availability = availability
    source.expires_at = expires_at
    source.failed_at = None
    db.flush()
    return source
