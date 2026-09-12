"""Select, validate, cache, and refresh lawful catalog audio sources."""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session

import catalog_repository
import models
from catalog_domain import TrackAvailability
from music import MusicProviderAdapter, ProviderError


class CanonicalTrackNotFound(LookupError):
    pass


_SOURCE_PRIORITY = {
    "local": 0,
    "upload": 0,
    "anonymous_full": 1,
    "public_preview": 2,
    "legal_public_fallback": 3,
}
_PROVIDER_PRIORITY = {"local": -1, "netease": 0, "qq": 1, "audius": 2}
_RELATIVE_AUDIO_PREFIXES = (
    "/api/music/",
    "/uploads/music_rooms/",
)
_DEFAULT_CACHE_TTL = timedelta(minutes=15)


def is_safe_playback_url(
    value: object,
    approved_hosts: set[str] | frozenset[str],
) -> bool:
    url = str(value or "").strip()
    if not url or any(ord(character) < 32 for character in url) or "\\" in url:
        return False
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError:
        return False
    if not parsed.scheme and not parsed.netloc:
        if not url.startswith("/") or url.startswith("//"):
            return False
        decoded_segments = unquote(parsed.path).split("/")
        if ".." in decoded_segments:
            return False
        return parsed.path.startswith(_RELATIVE_AUDIO_PREFIXES)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.username or parsed.password or not hostname:
        return False
    return hostname.lower() in {host.lower() for host in approved_hosts}


def _provider_for_source(
    db: Session,
    source: models.TrackAudioSource,
) -> str | None:
    if source.source_type in {"local", "upload"}:
        return "local"
    if source.provider_mapping_id is None:
        return None
    mapping = db.get(models.TrackProviderMapping, source.provider_mapping_id)
    return mapping.provider if mapping is not None else None


def _approved_hosts(
    registry: dict[str, MusicProviderAdapter],
    provider: str | None,
) -> frozenset[str]:
    adapter = registry.get(provider or "")
    return frozenset(getattr(adapter, "approved_audio_hosts", frozenset()))


def _payload(
    *,
    availability: str,
    playback_url: str | None,
    expires_at: datetime | None,
    source_type: str,
    provider: str | None,
    unavailable_reason: str | None = None,
) -> dict[str, object]:
    payload = {
        "availability": availability,
        "playback_url": playback_url,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "source_type": source_type,
        "provider": provider,
    }
    if unavailable_reason:
        payload["unavailable_reason"] = unavailable_reason
    return payload


def _cached_source(
    db: Session,
    canonical_id: int,
    registry: dict[str, MusicProviderAdapter],
    now: datetime,
    force_refresh: bool,
    provider: str | None = None,
    provider_track_id: str | None = None,
) -> models.TrackAudioSource | None:
    sources = catalog_repository.audio_sources_for_track(db, canonical_id)
    sources.sort(
        key=lambda source: (
            _SOURCE_PRIORITY.get(source.source_type, 99),
            source.id or 0,
        )
    )
    for source in sources:
        is_local = source.source_type in {"local", "upload"}
        expired = source.expires_at is not None and source.expires_at <= now
        if expired:
            source.availability = TrackAvailability.UNAVAILABLE.value
            source.failed_at = now
            continue
        if force_refresh and not is_local:
            continue
        if source.failed_at is not None or source.availability == "unavailable":
            continue
        source_provider = _provider_for_source(db, source)
        if provider is not None and source_provider != provider:
            continue
        if provider_track_id is not None and source.provider_mapping_id is not None:
            mapping = db.get(models.TrackProviderMapping, source.provider_mapping_id)
            if mapping is None or mapping.provider_track_id != provider_track_id:
                continue
        if is_safe_playback_url(
            source.playback_url,
            _approved_hosts(registry, source_provider),
        ):
            return source
    return None


async def resolve_audio(
    db: Session,
    canonical_id: int,
    registry: dict[str, MusicProviderAdapter],
    *,
    now: datetime | None = None,
    force_refresh: bool = False,
    provider: str | None = None,
    provider_track_id: str | None = None,
) -> dict[str, object]:
    canonical = db.get(models.CanonicalTrack, canonical_id)
    if canonical is None:
        raise CanonicalTrackNotFound(canonical_id)
    current_time = now or datetime.utcnow()

    cached = _cached_source(
        db,
        canonical_id,
        registry,
        current_time,
        force_refresh,
        provider=provider,
        provider_track_id=provider_track_id,
    )
    if cached is not None:
        provider = _provider_for_source(db, cached)
        db.commit()
        return _payload(
            availability=cached.availability,
            playback_url=cached.playback_url,
            expires_at=cached.expires_at,
            source_type=cached.source_type,
            provider=provider,
        )

    mappings = (
        db.query(models.TrackProviderMapping)
        .filter(models.TrackProviderMapping.canonical_track_id == canonical_id)
        .all()
    )
    mappings = [
        mapping
        for mapping in mappings
        if (provider is None or mapping.provider == provider)
        and (provider_track_id is None or mapping.provider_track_id == provider_track_id)
    ]
    mappings.sort(
        key=lambda mapping: (
            0 if mapping.availability == "playable" else 1,
            _PROVIDER_PRIORITY.get(mapping.provider, 100),
            mapping.id,
        )
    )
    for mapping in mappings:
        adapter = registry.get(mapping.provider)
        if adapter is None:
            continue
        try:
            resolution = await adapter.resolve(mapping)
        except ProviderError:
            continue
        if (
            resolution.availability is TrackAvailability.UNAVAILABLE
            or not resolution.playback_url
            or not is_safe_playback_url(
                resolution.playback_url,
                _approved_hosts(registry, mapping.provider),
            )
        ):
            continue
        expires_at = resolution.expires_at or current_time + _DEFAULT_CACHE_TTL
        source = catalog_repository.upsert_audio_source(
            db,
            canonical_id=canonical_id,
            provider_mapping_id=mapping.id,
            source_type=resolution.source_type,
            playback_url=resolution.playback_url,
            availability=resolution.availability.value,
            expires_at=expires_at,
        )
        db.commit()
        return _payload(
            availability=source.availability,
            playback_url=source.playback_url,
            expires_at=source.expires_at,
            source_type=source.source_type,
            provider=mapping.provider,
        )

    db.commit()
    requires_membership = any(
        mapping.fee is not None and mapping.fee > 0
        for mapping in mappings
    )
    return _payload(
        availability=TrackAvailability.UNAVAILABLE.value,
        playback_url=None,
        expires_at=None,
        source_type="unavailable",
        provider=None,
        unavailable_reason=(
            "需要会员权限，或服务器配置的音乐账号无权播放这首歌"
            if requires_membership
            else "所有已配置来源都无法提供可播放地址"
        ),
    )
