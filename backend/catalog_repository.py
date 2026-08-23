"""Persistence helpers for the provider-neutral music catalog."""

from __future__ import annotations

import json
from typing import Iterable
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session

import models
from catalog_domain import CanonicalGroup, TrackAvailability


_METADATA_LIMIT_BYTES = 16_384
_PROVIDER_ORDER = {"local": -1, "netease": 0, "qq": 1, "audius": 2}
_AVAILABILITY_ORDER = {
    TrackAvailability.PLAYABLE.value: 0,
    TrackAvailability.PREVIEW.value: 1,
    TrackAvailability.UNAVAILABLE.value: 2,
}


def safe_artwork_url(value: object) -> str | None:
    url = str(value or "").strip()
    if not url or any(ord(character) < 32 for character in url) or "\\" in url:
        return None
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError:
        return None
    if not parsed.scheme and not parsed.netloc:
        if not url.startswith("/") or url.startswith("//"):
            return None
        if ".." in unquote(parsed.path).split("/"):
            return None
        return url if parsed.path.startswith(("/api/", "/uploads/")) else None
    if parsed.scheme not in {"http", "https"} or not hostname:
        return None
    if parsed.username or parsed.password:
        return None
    return url


def _group_artwork(group: CanonicalGroup) -> str | None:
    return next(
        (
            safe
            for track in group.providers
            if (safe := safe_artwork_url(track.artwork_url)) is not None
        ),
        None,
    )


def _bounded_metadata(value: object) -> str:
    try:
        encoded = json.dumps(
            dict(value or {}),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
    except (TypeError, ValueError):
        return "{}"
    if len(encoded.encode("utf-8")) > _METADATA_LIMIT_BYTES:
        return '{"truncated":true}'
    return encoded


def provider_mapping(
    db: Session,
    provider: str,
    provider_track_id: str,
) -> models.TrackProviderMapping | None:
    return (
        db.query(models.TrackProviderMapping)
        .filter(
            models.TrackProviderMapping.provider == str(provider).strip().lower(),
            models.TrackProviderMapping.provider_track_id
            == str(provider_track_id).strip(),
        )
        .one_or_none()
    )


def _identity_candidate(
    db: Session,
    group: CanonicalGroup,
) -> models.CanonicalTrack | None:
    if group.isrc:
        exact = (
            db.query(models.CanonicalTrack)
            .filter(models.CanonicalTrack.isrc == group.isrc)
            .order_by(models.CanonicalTrack.id)
            .first()
        )
        if exact is not None:
            return exact

    candidates = (
        db.query(models.CanonicalTrack)
        .filter(
            models.CanonicalTrack.normalized_title == group.normalized_title,
            models.CanonicalTrack.normalized_artist == group.normalized_artist,
        )
        .order_by(models.CanonicalTrack.id)
        .all()
    )
    return next(
        (
            item
            for item in candidates
            if item.duration_seconds == 0
            or group.duration_seconds == 0
            or abs(item.duration_seconds - group.duration_seconds) <= 3
        ),
        None,
    )


def _canonical_for_group(
    db: Session,
    group: CanonicalGroup,
) -> models.CanonicalTrack:
    existing_mappings = [
        mapping
        for track in group.providers
        if (
            mapping := provider_mapping(
                db,
                track.provider,
                track.provider_track_id,
            )
        )
        is not None
    ]
    if existing_mappings:
        return min(existing_mappings, key=lambda item: item.canonical_track_id).canonical_track

    existing = _identity_candidate(db, group)
    if existing is not None:
        return existing

    canonical = models.CanonicalTrack(
        title=group.title,
        normalized_title=group.normalized_title,
        primary_artist=group.primary_artist,
        normalized_artist=group.normalized_artist,
        album=group.album,
        duration_seconds=group.duration_seconds,
        isrc=group.isrc,
        artwork_url=_group_artwork(group),
        availability=group.availability.value,
    )
    db.add(canonical)
    db.flush()
    return canonical


def _update_canonical(
    canonical: models.CanonicalTrack,
    group: CanonicalGroup,
) -> None:
    canonical.title = group.title
    canonical.normalized_title = group.normalized_title
    canonical.primary_artist = group.primary_artist
    canonical.normalized_artist = group.normalized_artist
    canonical.album = group.album or canonical.album
    canonical.duration_seconds = group.duration_seconds or canonical.duration_seconds
    canonical.isrc = group.isrc or canonical.isrc
    canonical.artwork_url = _group_artwork(group) or safe_artwork_url(
        canonical.artwork_url
    )


def _upsert_mapping(
    db: Session,
    canonical: models.CanonicalTrack,
    track,
) -> models.TrackProviderMapping:
    mapping = provider_mapping(db, track.provider, track.provider_track_id)
    if mapping is None:
        mapping = models.TrackProviderMapping(
            canonical_track_id=canonical.id,
            provider=track.provider,
            provider_track_id=track.provider_track_id,
        )
        db.add(mapping)
    else:
        mapping.canonical_track_id = canonical.id
    mapping.media_mid = track.media_mid
    mapping.fee = track.fee
    mapping.region = track.region
    mapping.availability = track.availability.value
    mapping.metadata_json = _bounded_metadata(track.metadata)
    return mapping


def _refresh_availability(
    db: Session,
    canonical: models.CanonicalTrack,
) -> None:
    db.flush()
    values = [
        row.availability
        for row in (
            db.query(models.TrackProviderMapping)
            .filter(
                models.TrackProviderMapping.canonical_track_id == canonical.id,
            )
            .all()
        )
    ]
    canonical.availability = min(
        values or [TrackAvailability.UNAVAILABLE.value],
        key=lambda value: _AVAILABILITY_ORDER.get(value, 99),
    )


def upsert_canonical_groups(
    db: Session,
    groups: Iterable[CanonicalGroup],
) -> list[models.CanonicalTrack]:
    persisted: list[models.CanonicalTrack] = []
    for group in groups:
        if not isinstance(group, CanonicalGroup):
            raise TypeError("upsert_canonical_groups requires CanonicalGroup values")
        canonical = _canonical_for_group(db, group)
        _update_canonical(canonical, group)
        for track in group.providers:
            _upsert_mapping(db, canonical, track)
        _refresh_availability(db, canonical)
        persisted.append(canonical)
    db.commit()
    for canonical in persisted:
        db.refresh(canonical)
    return persisted


def canonical_payload(db: Session, canonical_id: int) -> dict[str, object] | None:
    canonical = db.get(models.CanonicalTrack, canonical_id)
    if canonical is None:
        return None
    mappings = (
        db.query(models.TrackProviderMapping)
        .filter(models.TrackProviderMapping.canonical_track_id == canonical.id)
        .all()
    )
    mappings.sort(
        key=lambda item: (
            _PROVIDER_ORDER.get(item.provider, 100),
            item.provider,
            item.provider_track_id,
        )
    )
    return {
        "id": canonical.id,
        "title": canonical.title,
        "artist": canonical.primary_artist,
        "album": canonical.album,
        "duration_seconds": canonical.duration_seconds,
        "isrc": canonical.isrc,
        "artwork_url": safe_artwork_url(canonical.artwork_url),
        "availability": canonical.availability,
        "providers": [
            {
                "provider": mapping.provider,
                "provider_track_id": mapping.provider_track_id,
                "media_mid": mapping.media_mid,
                "fee": mapping.fee,
                "region": mapping.region,
                "availability": mapping.availability,
            }
            for mapping in mappings
        ],
    }


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
    valid.sort(key=lambda row: (_PROVIDER_ORDER.get(row.provider, 100), row.id))
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
