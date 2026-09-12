"""Public Audius catalog and stream adapter."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from catalog_domain import ProviderTrack, TrackAvailability
from .base import MusicProviderAdapter, ProviderLyrics, ProviderResolution


_SAFE_TRACK_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def _value(source: object, name: str, default=None):
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _text(value: object, limit: int) -> str | None:
    normalized = str(value or "").strip()
    return normalized[:limit] or None


class AudiusProviderAdapter(MusicProviderAdapter):
    provider = "audius"

    def __init__(
        self,
        base_url: str = "https://api.audius.co/v1",
        timeout_seconds: float = 5,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, timeout_seconds, transport=transport)
        host = urlparse(self.base_url).hostname
        self.approved_audio_hosts = frozenset({host}) if host else frozenset()

    def _normalize(self, item: object) -> ProviderTrack | None:
        if not isinstance(item, dict):
            return None
        track_id = _text(item.get("id"), 120)
        title = _text(item.get("title"), 300)
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        artist = _text(user.get("name") or user.get("handle"), 500)
        if not track_id or not title or not artist or not _SAFE_TRACK_ID.fullmatch(track_id):
            return None
        artwork = item.get("artwork") if isinstance(item.get("artwork"), dict) else {}
        try:
            duration = max(0, min(round(float(item.get("duration") or 0)), 86_400))
        except (TypeError, ValueError):
            duration = 0
        return ProviderTrack(
            provider=self.provider,
            provider_track_id=track_id,
            title=title,
            artist=artist,
            album=_text(item.get("album") or item.get("genre") or item.get("mood"), 300),
            duration_seconds=duration,
            isrc=_text(item.get("isrc"), 32),
            artwork_url=_text(artwork.get("480x480") or artwork.get("150x150"), 1000),
            availability=(
                TrackAvailability.PLAYABLE
                if item.get("is_streamable", True) is True
                else TrackAvailability.UNAVAILABLE
            ),
            metadata={
                "source": "audius",
                "source_url": f"https://audius.co/tracks/{track_id}",
            },
        )

    async def search(self, query: str, limit: int) -> list[ProviderTrack]:
        payload = await self._request_json(
            "/tracks/search",
            params={"query": str(query).strip(), "limit": max(1, min(int(limit), 30))},
        )
        items = payload.get("data")
        if not isinstance(items, list):
            return []
        return [track for item in items if (track := self._normalize(item)) is not None]

    async def trending(self, limit: int = 18) -> list[ProviderTrack]:
        payload = await self._request_json(
            "/tracks/trending",
            params={"limit": max(1, min(int(limit), 30)), "time": "week"},
        )
        items = payload.get("data")
        if not isinstance(items, list):
            return []
        return [
            track
            for item in items
            if (track := self._normalize(item)) is not None
            and track.availability is TrackAvailability.PLAYABLE
        ]

    async def get_track(self, track_id: str) -> ProviderTrack | None:
        if not _SAFE_TRACK_ID.fullmatch(str(track_id or "")):
            return None
        payload = await self._request_json(f"/tracks/{track_id}")
        item = payload.get("data")
        track = self._normalize(item)
        if track is None or track.availability is TrackAvailability.UNAVAILABLE:
            return None
        return track

    async def resolve(self, mapping: object) -> ProviderResolution:
        track_id = _text(_value(mapping, "provider_track_id"), 120)
        if not track_id or not _SAFE_TRACK_ID.fullmatch(track_id):
            return ProviderResolution(
                provider=self.provider,
                availability=TrackAvailability.UNAVAILABLE,
                playback_url=None,
                source_type="unavailable",
            )
        payload = await self._request_json(f"/tracks/{track_id}")
        item = payload.get("data")
        if not isinstance(item, dict) or item.get("is_streamable", True) is not True:
            return ProviderResolution(
                provider=self.provider,
                availability=TrackAvailability.UNAVAILABLE,
                playback_url=None,
                source_type="unavailable",
            )
        return ProviderResolution(
            provider=self.provider,
            availability=TrackAvailability.PLAYABLE,
            playback_url=f"{self.base_url}/tracks/{track_id}/stream",
            source_type="anonymous_full",
        )

    async def lyrics(
        self,
        mapping: object,
        language: str = "original",
    ) -> ProviderLyrics:
        return ProviderLyrics(
            provider=self.provider,
            language=_text(language, 30) or "original",
            timed_text="",
        )


__all__ = ["AudiusProviderAdapter"]
