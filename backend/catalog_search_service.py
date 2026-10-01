"""Provider fan-out and canonical catalog search."""

from __future__ import annotations

import asyncio
from typing import Iterable, Mapping

from sqlalchemy.orm import Session

import catalog_repository
from catalog_domain import ProviderTrack, canonicalize_tracks, normalize_identity
from music import MusicProviderAdapter


class AllProvidersUnavailable(RuntimeError):
    """Every requested provider failed before returning a valid result."""


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
    payloads = [
        payload
        for canonical in persisted
        if (payload := catalog_repository.canonical_payload(db, canonical.id)) is not None
    ]
    first_seen: dict[tuple[str, str], int] = {}
    for index, track in enumerate(tracks):
        first_seen.setdefault((track.provider, track.provider_track_id), index)
    exact_title = normalize_identity(query)
    items = sorted(
        payloads,
        key=lambda item: (
            0 if normalize_identity(item.get("title")) == exact_title else 1,
            min(
                (first_seen.get((provider.get("provider"), provider.get("provider_track_id")), len(tracks))
                 for provider in item.get("providers", [])),
            ),
        ),
    )
    return {
        "query": str(query).strip(),
        "items": items,
        "providers": statuses,
    }
