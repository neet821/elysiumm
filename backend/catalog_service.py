"""Fault-tolerant orchestration for the provider-neutral music catalog."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import re
from typing import Iterable, Mapping

from sqlalchemy.orm import Session

import catalog_repository
from catalog_domain import ProviderTrack, canonicalize_tracks
import models
from music_providers import MusicProviderAdapter, ProviderError


class AllProvidersUnavailable(RuntimeError):
    """Every requested provider failed before returning a valid result."""


class CatalogTrackNotFound(LookupError):
    pass


_LRC_TAG = re.compile(r"\[(\d{1,3}):(\d{2}(?:\.\d{1,3})?)\]")
_PROVIDER_ORDER = {"local": -1, "netease": 0, "qq": 1, "audius": 2}
_LYRICS_TTL = timedelta(days=1)


def normalize_timed_lyrics(value: object) -> list[dict[str, object]]:
    lines: list[dict[str, object]] = []
    for raw_line in str(value or "").splitlines()[:5000]:
        matches = list(_LRC_TAG.finditer(raw_line))
        if not matches:
            continue
        text = _LRC_TAG.sub("", raw_line).strip()[:1000]
        if not text:
            continue
        for match in matches:
            seconds = round(int(match.group(1)) * 60 + float(match.group(2)), 3)
            lines.append({"time": seconds, "text": text})
    lines.sort(key=lambda item: (item["time"], item["text"]))
    return lines


def _lyrics_payload(
    canonical_id: int,
    provider: str | None,
    language: str,
    timed_text: str,
    translation_text: str | None,
    *,
    cached: bool,
) -> dict[str, object]:
    return {
        "track_id": canonical_id,
        "provider": provider,
        "language": language,
        "lines": normalize_timed_lyrics(timed_text),
        "translation": normalize_timed_lyrics(translation_text),
        "cached": cached,
    }


async def get_catalog_lyrics(
    db: Session,
    canonical_id: int,
    registry: Mapping[str, MusicProviderAdapter],
    *,
    language: str = "original",
    provider: str | None = None,
    provider_track_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    if db.get(models.CanonicalTrack, canonical_id) is None:
        raise CatalogTrackNotFound(canonical_id)
    current_time = now or datetime.utcnow()
    cached = catalog_repository.cached_lyrics(
        db,
        canonical_id,
        language,
        current_time,
    )
    if cached is not None and (provider is None or cached.provider == provider):
        return _lyrics_payload(
            canonical_id,
            cached.provider,
            language,
            cached.timed_text or "",
            cached.translation_text,
            cached=True,
        )

    mappings = (
        db.query(models.TrackProviderMapping)
        .filter(models.TrackProviderMapping.canonical_track_id == canonical_id)
        .all()
    )
    mappings.sort(key=lambda item: (_PROVIDER_ORDER.get(item.provider, 100), item.id))
    mappings = [
        mapping
        for mapping in mappings
        if (provider is None or mapping.provider == provider)
        and (provider_track_id is None or mapping.provider_track_id == provider_track_id)
    ]
    empty_result = None
    for mapping in mappings:
        adapter = registry.get(mapping.provider)
        if adapter is None:
            continue
        try:
            result = await adapter.lyrics(mapping, language=language)
        except ProviderError:
            continue
        if not result.timed_text.strip():
            empty_result = empty_result or (mapping, result)
            continue
        row = catalog_repository.upsert_lyrics(
            db,
            canonical_id=canonical_id,
            provider_mapping_id=mapping.id,
            provider=mapping.provider,
            language=language,
            timed_text=result.timed_text,
            translation_text=result.translation_text,
            fetched_at=current_time,
            expires_at=current_time + _LYRICS_TTL,
        )
        db.commit()
        return _lyrics_payload(
            canonical_id,
            row.provider,
            language,
            row.timed_text or "",
            row.translation_text,
            cached=False,
        )

    if empty_result is not None:
        mapping, result = empty_result
        catalog_repository.upsert_lyrics(
            db,
            canonical_id=canonical_id,
            provider_mapping_id=mapping.id,
            provider=mapping.provider,
            language=language,
            timed_text="",
            translation_text=None,
            fetched_at=current_time,
            expires_at=current_time + _LYRICS_TTL,
        )
        db.commit()
        return _lyrics_payload(
            canonical_id,
            mapping.provider,
            language,
            "",
            None,
            cached=False,
        )
    return _lyrics_payload(
        canonical_id,
        None,
        language,
        "",
        None,
        cached=False,
    )


async def search_catalog(
    db: Session,
    query: str,
    providers: Iterable[str],
    limit: int,
    registry: Mapping[str, MusicProviderAdapter],
) -> dict[str, object]:
    requested = list(dict.fromkeys(str(provider).strip().lower() for provider in providers))
    tasks = [registry[provider].search(str(query).strip(), limit) for provider in requested]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    tracks: list[ProviderTrack] = []
    statuses: list[dict[str, object]] = []
    failures = 0
    for provider, result in zip(requested, results):
        if isinstance(result, BaseException):
            failures += 1
            statuses.append({"provider": provider, "status": "error", "count": 0})
            continue
        valid = [
            track
            for track in result
            if isinstance(track, ProviderTrack) and track.provider == provider
        ]
        tracks.extend(valid)
        statuses.append({"provider": provider, "status": "ok", "count": len(valid)})

    if requested and failures == len(requested):
        raise AllProvidersUnavailable("all requested music providers failed")

    groups = canonicalize_tracks(tracks)
    persisted = catalog_repository.upsert_canonical_groups(db, groups) if groups else []
    items = [
        payload
        for canonical in persisted
        if (payload := catalog_repository.canonical_payload(db, canonical.id)) is not None
    ]
    return {
        "query": str(query).strip(),
        "items": items,
        "providers": statuses,
    }
