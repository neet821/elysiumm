"""Anonymous NetEase and QQ catalog adapters backed by Mineradio."""

from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urlencode

import httpx

from catalog_domain import ProviderTrack, TrackAvailability
from music_providers.base import (
    MusicProviderAdapter,
    ProviderError,
    ProviderLyrics,
    ProviderResolution,
)


_SAFE_TRACK_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def _value(source: object, name: str, default=None):
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _text(value: object, limit: int) -> str | None:
    normalized = str(value or "").strip()
    return normalized[:limit] or None


def _duration_seconds(value: object) -> int:
    try:
        duration = float(value or 0)
    except (TypeError, ValueError):
        return 0
    if duration > 10_000:
        duration /= 1000
    return max(0, min(round(duration), 86_400))


def _availability(
    item: dict[str, object],
    *,
    vip_entitled: bool = False,
) -> TrackAvailability:
    if item.get("trial") or item.get("preview") or item.get("preview_url"):
        return TrackAvailability.PREVIEW
    if item.get("playable") is True:
        return TrackAvailability.PLAYABLE
    try:
        fee = int(item.get("fee", -1))
    except (TypeError, ValueError):
        fee = -1
    return (
        TrackAvailability.PLAYABLE
        if fee == 0 or (fee == 1 and vip_entitled)
        else TrackAvailability.UNAVAILABLE
    )


class MineradioProviderAdapter(MusicProviderAdapter):
    search_path: str
    lyrics_path: str

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5,
        *,
        internal_token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url,
            timeout_seconds,
            internal_token=internal_token,
            transport=transport,
        )

    def _track_id(self, item: dict[str, object]) -> str | None:
        if self.provider == "qq":
            return _text(
                item.get("mid") or item.get("songmid") or item.get("id"),
                120,
            )
        return _text(item.get("id"), 120)

    def _normalize(
        self,
        item: object,
        *,
        vip_entitled: bool = False,
    ) -> ProviderTrack | None:
        if not isinstance(item, dict):
            return None
        track_id = self._track_id(item)
        title = _text(item.get("name") or item.get("title"), 300)
        artist = _text(item.get("artist"), 500)
        if not track_id or not title or not artist or not _SAFE_TRACK_ID.fullmatch(track_id):
            return None
        return ProviderTrack(
            provider=self.provider,
            provider_track_id=track_id,
            title=title,
            artist=artist,
            album=_text(item.get("album"), 300),
            duration_seconds=_duration_seconds(
                item.get("duration") or item.get("duration_seconds")
            ),
            isrc=_text(item.get("isrc"), 32),
            artwork_url=_text(item.get("cover") or item.get("artwork_url"), 1000),
            availability=_availability(item, vip_entitled=vip_entitled),
            media_mid=(
                _text(item.get("mediaMid") or item.get("media_mid"), 255)
                if self.provider == "qq"
                else None
            ),
            fee=(
                int(item["fee"])
                if str(item.get("fee", "")).lstrip("-").isdigit()
                else None
            ),
            region=_text(item.get("region"), 50),
            metadata={"source": "mineradio"},
        )

    async def search(self, query: str, limit: int) -> list[ProviderTrack]:
        vip_entitled = False
        if self.provider == "netease" and self.internal_token:
            try:
                status = await self._request_json("/api/login/status")
                vip_entitled = bool(
                    status.get("loggedIn") is True
                    and (
                        status.get("isVip") is True
                        or str(status.get("vipLevel") or "").lower() in {"vip", "svip"}
                    )
                )
            except ProviderError:
                pass
        payload = await self._request_json(
            self.search_path,
            params={"keywords": str(query).strip(), "limit": max(1, min(int(limit), 30))},
        )
        songs = payload.get("songs")
        if not isinstance(songs, list):
            return []
        return [
            track
            for item in songs
            if (track := self._normalize(item, vip_entitled=vip_entitled)) is not None
        ]

    async def resolve(self, mapping: object) -> ProviderResolution:
        track_id = _text(_value(mapping, "provider_track_id"), 120)
        try:
            availability = TrackAvailability(_value(mapping, "availability"))
        except ValueError:
            availability = TrackAvailability.UNAVAILABLE
        if (
            not track_id
            or not _SAFE_TRACK_ID.fullmatch(track_id)
            or availability is TrackAvailability.UNAVAILABLE
        ):
            return ProviderResolution(
                provider=self.provider,
                availability=TrackAvailability.UNAVAILABLE,
                playback_url=None,
                source_type="unavailable",
            )

        query: dict[str, str] = {"provider": self.provider, "id": track_id}
        media_mid = _text(_value(mapping, "media_mid"), 255)
        if self.provider == "qq" and media_mid and _SAFE_TRACK_ID.fullmatch(media_mid):
            query["mediaMid"] = media_mid
        try:
            check_path = "/api/internal/room/check" if self.internal_token else "/api/room/check"
            check = await self._request_json(check_path, params=query)
        except ProviderError:
            return ProviderResolution(
                provider=self.provider,
                availability=TrackAvailability.UNAVAILABLE,
                playback_url=None,
                source_type="unavailable",
            )
        ticket = _text(check.get("ticket"), 2048)
        if check.get("playable") is not True or (self.internal_token and not ticket):
            return ProviderResolution(
                provider=self.provider,
                availability=TrackAvailability.UNAVAILABLE,
                playback_url=None,
                source_type="unavailable",
            )
        return ProviderResolution(
            provider=self.provider,
            availability=availability,
            playback_url=f"/mineradio-api/room/audio?{urlencode({**query, **({'ticket': ticket} if ticket else {})})}",
            source_type=(
                "public_preview"
                if availability is TrackAvailability.PREVIEW
                else "anonymous_full"
            ),
            expires_at=(
                datetime.fromisoformat(str(check["expires_at"]))
                if check.get("expires_at")
                else None
            ),
        )

    async def lyrics(
        self,
        mapping: object,
        language: str = "original",
    ) -> ProviderLyrics:
        track_id = _text(_value(mapping, "provider_track_id"), 120) or ""
        params = {"mid" if self.provider == "qq" else "id": track_id}
        payload = await self._request_json(self.lyrics_path, params=params)
        return ProviderLyrics(
            provider=self.provider,
            language=_text(language, 30) or "original",
            timed_text=_text(payload.get("lyric") or payload.get("yrc"), 500_000) or "",
            translation_text=_text(
                payload.get("tlyric") or payload.get("trans") or payload.get("translation"),
                500_000,
            ),
        )


class NeteaseProviderAdapter(MineradioProviderAdapter):
    provider = "netease"
    search_path = "/api/search"
    lyrics_path = "/api/lyric"


class QQProviderAdapter(MineradioProviderAdapter):
    provider = "qq"
    search_path = "/api/qq/search"
    lyrics_path = "/api/qq/lyric"
