from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from catalog_domain import ProviderTrack, TrackAvailability

from .base import ProviderError, ProviderLyrics, ProviderResolution
from .direct import DirectMusicProvider
from .provider_common import (
    _USER_AGENT,
    _artist_names,
    _availability,
    _duration_seconds,
    _safe_fee,
    _text,
)

_SAFE_NUMERIC_ID = re.compile(r"^[0-9]{1,32}$")
NETEASE_PLAYLIST_PAGE_SIZE = 200
_NETEASE_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://music.163.com/",
    "User-Agent": _USER_AGENT,
}


NETEASE_PLAYLIST_PAGE_SIZE = 200


_NETEASE_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://music.163.com/",
    "User-Agent": _USER_AGENT,
}


class NeteaseProviderAdapter(DirectMusicProvider):
    provider = "netease"
    headers = _NETEASE_HEADERS
    approved_audio_hosts = frozenset({"music.126.net", "*.music.126.net"})

    def _normalize(self, item: object) -> ProviderTrack | None:
        if not isinstance(item, dict):
            return None
        track_id = _text(item.get("id"), 120)
        title = _text(item.get("name") or item.get("title"), 300)
        artists = item.get("artists") or item.get("ar")
        artist = _artist_names(artists if artists is not None else item.get("artist"))
        album = item.get("album") or item.get("al") or {}
        if not isinstance(album, dict):
            album = {"name": album}
        artwork = album.get("picUrl") or item.get("cover") or item.get("artwork_url")
        if not track_id or not _SAFE_NUMERIC_ID.fullmatch(track_id) or not title:
            return None
        return ProviderTrack(
            provider=self.provider,
            provider_track_id=track_id,
            title=title,
            artist=artist,
            album=_text(album.get("name"), 300),
            duration_seconds=_duration_seconds(item.get("dt") or item.get("duration")),
            # noCopyrightRcmd is a recommendation object, not an ISRC.
            isrc=_text(item.get("isrc"), 32),
            artwork_url=_text(artwork, 1000),
            availability=_availability(item),
            fee=_safe_fee(item.get("fee")),
            metadata={"source": "netease-direct"},
        )

    async def search(self, query: str, limit: int) -> list[ProviderTrack]:
        payload = await self._request_json(
            "GET",
            "/cloudsearch",
            params={
                "keywords": str(query).strip(),
                "type": 1,
                "offset": 0,
                "limit": max(1, min(int(limit), 30)),
            },
        )
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        songs = result.get("songs") if isinstance(result, dict) else []
        if not isinstance(songs, list):
            return []
        return [track for item in songs if (track := self._normalize(item)) is not None]

    async def fetch_public_playlist(self, playlist_id: str) -> dict[str, object]:
        """Fetch a bounded public playlist copy without sending server credentials."""

        if not _SAFE_NUMERIC_ID.fullmatch(str(playlist_id)):
            raise ProviderError("网易云歌单编号无效")
        detail = await self._request_json(
            "GET",
            "/playlist/detail",
            params={"id": playlist_id, "s": 0},
            include_credential=False,
        )
        try:
            code = int(detail.get("code", 200))
            playlist = detail.get("playlist")
            privacy = int(playlist.get("privacy")) if isinstance(playlist, dict) and playlist.get("privacy") is not None else None
            track_count = int(playlist.get("trackCount", 0)) if isinstance(playlist, dict) else -1
        except (TypeError, ValueError) as exc:
            raise ProviderError("网易云歌单返回了无效内容") from exc
        if code != 200 or not isinstance(playlist, dict):
            raise ProviderError("网易云歌单暂时无法读取")
        if privacy != 0:
            raise ProviderError("仅支持公开歌单")
        if track_count < 0:
            raise ProviderError("网易云歌单返回了无效歌曲数量")
        if track_count > 2000:
            raise ProviderError("歌单歌曲数量超过导入上限（2000 首）")

        songs: list[object] = []
        for offset in range(0, track_count, NETEASE_PLAYLIST_PAGE_SIZE):
            limit = min(NETEASE_PLAYLIST_PAGE_SIZE, track_count - offset)
            track_payload = await self._request_json(
                "GET",
                "/playlist/track/all",
                params={"id": playlist_id, "limit": limit, "offset": offset},
                include_credential=False,
            )
            try:
                track_code = int(track_payload.get("code", 200))
            except (TypeError, ValueError) as exc:
                raise ProviderError("网易云歌单返回了无效内容") from exc
            if track_code != 200:
                raise ProviderError("网易云歌单歌曲暂时无法读取")
            value = track_payload.get("songs")
            if not isinstance(value, list):
                value = track_payload.get("tracks")
            if isinstance(value, list):
                songs.extend(value[:limit])

        tracks: list[dict[str, object]] = []
        for index in range(track_count):
            raw = songs[index] if index < len(songs) else None
            track = self._normalize(raw)
            if track is not None:
                tracks.append({
                    "provider": self.provider,
                    "provider_track_id": track.provider_track_id,
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "artwork_url": track.artwork_url,
                    "duration_seconds": track.duration_seconds,
                    "availability": track.availability.value,
                    "missing": False,
                })
                continue
            raw_item = raw if isinstance(raw, dict) else {}
            tracks.append({
                "provider": self.provider,
                # If a row cannot be normalized, retain it as a visible missing
                # entry rather than making its unverified source id playable.
                "provider_track_id": None,
                "title": _text(raw_item.get("name") or raw_item.get("title"), 300)
                or f"未能读取的歌曲 #{index + 1}",
                "artist": _artist_names(raw_item.get("ar") or raw_item.get("artists") or raw_item.get("artist")),
                "album": None,
                "artwork_url": None,
                "duration_seconds": 0,
                "availability": TrackAvailability.UNAVAILABLE.value,
                "missing": True,
            })
        return {
            "provider": self.provider,
            "source_playlist_id": str(playlist_id),
            "name": _text(playlist.get("name"), 120) or "网易云导入歌单",
            "source_url": f"https://music.163.com/playlist?id={playlist_id}",
            "track_count": track_count,
            "tracks": tracks,
        }

    async def fetch_stream_url(self, track_id: str) -> tuple[str | None, datetime | None, bool]:
        if not _SAFE_NUMERIC_ID.fullmatch(track_id):
            return None, None, False
        payload = await self._request_json(
            "GET",
            "/song/url/v1",
            params={"id": track_id, "level": "standard"},
        )
        rows = payload.get("data")
        item = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
        url = _text(item.get("url"), 4096)
        if not url:
            return None, None, False
        expires = _safe_fee(item.get("expi"))
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires) if expires and expires > 0 else None
        return url, expiry, bool(item.get("freeTrialInfo"))

    async def resolve(self, mapping: object) -> ProviderResolution:
        track_id = _text(getattr(mapping, "provider_track_id", ""), 120) or ""
        try:
            availability = TrackAvailability(getattr(mapping, "availability", "unavailable"))
        except ValueError:
            availability = TrackAvailability.UNAVAILABLE
        if availability is TrackAvailability.UNAVAILABLE:
            return ProviderResolution(self.provider, availability, None, "unavailable")
        url, expires, trial = await self.fetch_stream_url(track_id)
        if not url:
            return ProviderResolution(self.provider, TrackAvailability.UNAVAILABLE, None, "unavailable")
        return self._direct_resolution(
            self.provider,
            track_id,
            TrackAvailability.PREVIEW if trial else availability,
            expires_at=expires,
        )

    async def lyrics(self, mapping: object, language: str = "original") -> ProviderLyrics:
        track_id = _text(getattr(mapping, "provider_track_id", ""), 120) or ""
        if not _SAFE_NUMERIC_ID.fullmatch(track_id):
            raise ProviderError("网易云歌曲编号无效")
        payload = await self._request_json(
            "GET",
            "/api/song/lyric",
            params={"id": track_id, "lv": 1, "kv": 1, "tv": -1},
        )
        lyric = payload.get("lrc") if isinstance(payload.get("lrc"), dict) else {}
        translation = payload.get("tlyric") if isinstance(payload.get("tlyric"), dict) else {}
        return ProviderLyrics(
            self.provider,
            _text(language, 30) or "original",
            _text(lyric.get("lyric"), 500_000) or "",
            _text(translation.get("lyric"), 500_000),
        )
