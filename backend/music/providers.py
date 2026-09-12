"""Direct upstream adapters for Netease, QQ Music and Audius.

The browser only receives Elysium's provider-neutral contract. Provider
cookies remain root-owned files and are read by this module on the server;
they never enter release manifests or browser responses.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlencode

import httpx

from catalog_domain import ProviderTrack, TrackAvailability
from .base import (
    MAX_PROVIDER_RESPONSE_BYTES,
    MusicProviderAdapter,
    ProviderError,
    ProviderLyrics,
    ProviderResolution,
)


_SAFE_TRACK_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
_SAFE_NUMERIC_ID = re.compile(r"^[0-9]{1,32}$")
_USER_AGENT = "ElysiumMusic/1.0 (+https://elysiumm.top)"
_NETEASE_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://music.163.com/",
    "User-Agent": _USER_AGENT,
}
_QQ_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://y.qq.com/",
    "User-Agent": _USER_AGENT,
}


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


def _safe_fee(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _availability(item: dict[str, object]) -> TrackAvailability:
    if item.get("trial") or item.get("preview") or item.get("freeTrialInfo"):
        return TrackAvailability.PREVIEW
    fee = _safe_fee(item.get("fee"))
    if item.get("playable") is True or fee == 0:
        return TrackAvailability.PLAYABLE
    return TrackAvailability.UNAVAILABLE


def _artist_names(values: object) -> str:
    if not isinstance(values, list):
        return _text(values, 500) or "未知音乐人"
    names = [_text(item.get("name"), 120) for item in values if isinstance(item, dict)]
    return " / ".join(item for item in names if item) or "未知音乐人"


class DirectMusicProvider(MusicProviderAdapter):
    """Common bounded HTTP and credential handling for direct providers."""

    provider = ""
    headers: dict[str, str] = {}

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5,
        *,
        credential_path: Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, timeout_seconds, transport=transport)
        self.credential_path = credential_path.expanduser() if credential_path else None

    @classmethod
    def audius(cls, base_url: str, timeout_seconds: float = 5) -> "DirectMusicProvider":
        from .audius import AudiusProviderAdapter

        return AudiusProviderAdapter(base_url, timeout_seconds)

    def _credential(self) -> str:
        if self.credential_path is None or not self.credential_path.is_file():
            return ""
        try:
            return self.credential_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return ""

    def has_credential(self) -> bool:
        return bool(self._credential())

    def clear_credential(self) -> None:
        if self.credential_path is None:
            return
        try:
            self.credential_path.unlink(missing_ok=True)
        except OSError as exc:
            raise ProviderError("曲库凭据无法删除") from exc

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        request_headers = {**self.headers, **(headers or {})}
        credential = self._credential()
        if credential:
            request_headers["Cookie"] = credential
        content = b""
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout_seconds,
                    follow_redirects=False,
                    transport=self.transport,
                    trust_env=False,
                ) as client:
                    response = await client.request(
                        method,
                        path,
                        params=params,
                        json=payload,
                        headers=request_headers,
                    )
                    if response.status_code >= 500 and attempt == 0:
                        await asyncio.sleep(0.2)
                        continue
                    response.raise_for_status()
                    if int(response.headers.get("content-length", "0") or 0) > MAX_PROVIDER_RESPONSE_BYTES:
                        raise ProviderError("曲库返回内容过大")
                    content = await response.aread()
                    break
            except ProviderError:
                raise
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                raise ProviderError("曲库暂时不可用") from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise ProviderError("曲库暂时不可用") from exc
        if len(content) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ProviderError("曲库返回内容过大")
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("曲库返回了无效内容") from exc
        if not isinstance(value, dict):
            raise ProviderError("曲库返回了无效内容")
        return value

    async def _request_text(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
    ) -> str:
        request_headers = dict(self.headers)
        credential = self._credential()
        if credential:
            request_headers["Cookie"] = credential
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = await client.request(method, path, params=params, headers=request_headers)
                response.raise_for_status()
                body = await response.aread()
        except httpx.HTTPError as exc:
            raise ProviderError("曲库暂时不可用") from exc
        if len(body) > MAX_PROVIDER_RESPONSE_BYTES:
            raise ProviderError("曲库返回内容过大")
        return body.decode("utf-8", errors="replace")

    @staticmethod
    def _direct_resolution(
        provider: str,
        track_id: str,
        availability: TrackAvailability,
        *,
        expires_at: datetime | None = None,
        media_mid: str | None = None,
    ) -> ProviderResolution:
        query = {"provider": provider, "id": track_id}
        if media_mid:
            query["mediaMid"] = media_mid
        return ProviderResolution(
            provider=provider,
            availability=availability,
            playback_url=f"/api/music/stream/{provider}/{track_id}?{urlencode(query)}",
            source_type="public_preview" if availability is TrackAvailability.PREVIEW else "anonymous_full",
            expires_at=expires_at,
        )


class NeteaseProviderAdapter(DirectMusicProvider):
    provider = "netease"
    headers = _NETEASE_HEADERS

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
            isrc=_text(item.get("noCopyrightRcmd") or item.get("isrc"), 32),
            artwork_url=_text(artwork, 1000),
            availability=_availability(item),
            fee=_safe_fee(item.get("fee")),
            metadata={"source": "netease-direct"},
        )

    async def search(self, query: str, limit: int) -> list[ProviderTrack]:
        payload = await self._request_json(
            "GET",
            "/api/search/get/web",
            params={"s": str(query).strip(), "type": 1, "offset": 0, "limit": max(1, min(int(limit), 30))},
        )
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        songs = result.get("songs") if isinstance(result, dict) else []
        if not isinstance(songs, list):
            return []
        return [track for item in songs if (track := self._normalize(item)) is not None]

    async def fetch_stream_url(self, track_id: str) -> tuple[str | None, datetime | None, bool]:
        if not _SAFE_NUMERIC_ID.fullmatch(track_id):
            return None, None, False
        payload = await self._request_json(
            "GET",
            "/api/song/enhance/player/url/v1",
            params={"ids": f"[{track_id}]", "level": "standard", "encodeType": "aac"},
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


def _decode_qq_text(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    compact = "".join(raw.split())
    if len(compact) >= 8 and len(compact) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", compact) and "[" not in raw:
        try:
            decoded = base64.b64decode(compact).decode("utf-8", errors="replace").strip()
            if "[" in decoded or re.search(r"[\u4e00-\u9fff]", decoded):
                raw = decoded
        except (ValueError, UnicodeError):
            pass
    return raw.replace("\r\n", "\n").strip()


class QQProviderAdapter(DirectMusicProvider):
    provider = "qq"
    headers = _QQ_HEADERS
    # QQ's search endpoint lives on c.y.qq.com; detail, lyric and vkey calls
    # stay on the configurable u.y.qq.com API host.
    smartbox_path = "https://c.y.qq.com/splcloud/fcgi-bin/smartbox_new.fcg"
    musicu_path = "/cgi-bin/musicu.fcg"

    def _smartbox_params(self, query: str) -> dict[str, object]:
        return {
            "format": "json", "key": query, "g_tk": "5381", "loginUin": "0", "hostUin": "0",
            "inCharset": "utf8", "outCharset": "utf-8", "notice": "0", "platform": "yqq.json", "needNewCode": "0",
        }

    def _normalize(self, item: object, detail: dict[str, object] | None = None) -> ProviderTrack | None:
        if not isinstance(item, dict):
            return None
        raw = detail or item
        track_id = _text(raw.get("mid") or raw.get("songmid") or item.get("mid"), 120)
        title = _text(raw.get("name") or raw.get("songname") or item.get("name"), 300)
        artists = raw.get("singer") or raw.get("singers") or item.get("singer")
        artist = _artist_names(artists)
        album = raw.get("album") or {}
        if not isinstance(album, dict):
            album = {"name": album}
        album_mid = _text(album.get("mid") or raw.get("album_mid") or item.get("album_mid"), 120)
        artwork = raw.get("cover") or item.get("cover")
        if not artwork and album_mid:
            artwork = f"https://y.qq.com/music/photo_new/T002R300x300M000{album_mid}.jpg"
        if not track_id or not _SAFE_TRACK_ID.fullmatch(track_id) or not title:
            return None
        return ProviderTrack(
            provider=self.provider,
            provider_track_id=track_id,
            title=title,
            artist=artist,
            album=_text(album.get("name"), 300),
            duration_seconds=_duration_seconds(raw.get("interval") or raw.get("duration")),
            artwork_url=_text(artwork, 1000),
            availability=_availability(raw),
            media_mid=_text(raw.get("mediaMid") or raw.get("media_mid") or item.get("mediaMid"), 255),
            fee=_safe_fee(raw.get("fee") or ((raw.get("pay") or {}).get("pay_play") if isinstance(raw.get("pay"), dict) else None)),
            metadata={"source": "qq-direct"},
        )

    async def _detail(self, mid: str, fallback: dict[str, object]) -> dict[str, object]:
        payload = await self._request_json(
            "POST",
            self.musicu_path,
            payload={
                "comm": {"ct": 24, "cv": 0},
                "songinfo": {
                    "module": "music.pf_song_detail_svr",
                    "method": "get_song_detail_yqq",
                    "param": {"song_mid": mid},
                },
            },
        )
        block = payload.get("songinfo") if isinstance(payload.get("songinfo"), dict) else {}
        data = block.get("data") if isinstance(block, dict) and isinstance(block.get("data"), dict) else {}
        result = data.get("track_info") if isinstance(data, dict) and isinstance(data.get("track_info"), dict) else {}
        return result or fallback

    async def search(self, query: str, limit: int) -> list[ProviderTrack]:
        text = str(query).strip()
        if not text:
            return []
        payload = await self._request_json("GET", self.smartbox_path, params=self._smartbox_params(text))
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        songs = data.get("song", {}).get("itemlist") if isinstance(data.get("song"), dict) else []
        if not isinstance(songs, list):
            return []
        tracks: list[ProviderTrack] = []
        seen: set[str] = set()
        for item in songs[: max(1, min(int(limit), 12))]:
            if not isinstance(item, dict):
                continue
            mid = _text(item.get("mid") or item.get("songmid"), 120)
            if not mid or mid in seen:
                continue
            seen.add(mid)
            try:
                detail = await self._detail(mid, item)
            except ProviderError:
                detail = item
            track = self._normalize(item, detail)
            if track is not None:
                tracks.append(track)
        return tracks

    async def fetch_stream_url(self, track_id: str, media_mid: str | None = None) -> tuple[str | None, datetime | None, bool]:
        if not _SAFE_TRACK_ID.fullmatch(track_id):
            return None, None, False
        media_ids = [item for item in (media_mid, track_id) if item and _SAFE_TRACK_ID.fullmatch(item)]
        filenames = [f"M500{item}.mp3" for item in dict.fromkeys(media_ids)]
        payload = await self._request_json(
            "POST",
            self.musicu_path,
            payload={
                "comm": {"uin": "0", "format": "json", "ct": 24, "cv": 0},
                "req_0": {
                    "module": "vkey.GetVkeyServer",
                    "method": "CgiGetVkey",
                    "param": {
                        "guid": "10000000",
                        "songmid": [track_id],
                        "songtype": [0],
                        "uin": "0",
                        "loginflag": 1,
                        "platform": "20",
                        "filename": filenames,
                    },
                },
            },
        )
        block = payload.get("req_0") if isinstance(payload.get("req_0"), dict) else {}
        data = block.get("data") if isinstance(block.get("data"), dict) else {}
        rows = data.get("midurlinfo") if isinstance(data.get("midurlinfo"), list) else []
        row = next((item for item in rows if isinstance(item, dict) and item.get("purl")), None)
        if not row:
            return None, None, False
        prefix = data.get("sip", ["https://ws.stream.qqmusic.qq.com/"])
        stream_prefix = prefix[0] if isinstance(prefix, list) and prefix and isinstance(prefix[0], str) else "https://ws.stream.qqmusic.qq.com/"
        return f"{stream_prefix}{row['purl']}", datetime.now(timezone.utc) + timedelta(minutes=10), False

    async def resolve(self, mapping: object) -> ProviderResolution:
        track_id = _text(getattr(mapping, "provider_track_id", ""), 120) or ""
        try:
            availability = TrackAvailability(getattr(mapping, "availability", "unavailable"))
        except ValueError:
            availability = TrackAvailability.UNAVAILABLE
        if availability is TrackAvailability.UNAVAILABLE:
            return ProviderResolution(self.provider, availability, None, "unavailable")
        media_mid = _text(getattr(mapping, "media_mid", ""), 255)
        url, expires, trial = await self.fetch_stream_url(track_id, media_mid)
        if not url:
            return ProviderResolution(self.provider, TrackAvailability.UNAVAILABLE, None, "unavailable")
        return self._direct_resolution(self.provider, track_id, TrackAvailability.PREVIEW if trial else availability, expires_at=expires, media_mid=media_mid)

    async def lyrics(self, mapping: object, language: str = "original") -> ProviderLyrics:
        track_id = _text(getattr(mapping, "provider_track_id", ""), 120) or ""
        if not _SAFE_TRACK_ID.fullmatch(track_id):
            raise ProviderError("QQ 音乐歌曲编号无效")
        payload = await self._request_json(
            "POST",
            self.musicu_path,
            payload={
                "comm": {"ct": 24, "cv": 0},
                "lyric": {
                    "module": "music.musichallSong.PlayLyricInfo",
                    "method": "GetPlayLyricInfo",
                    "param": {"songMID": track_id},
                },
            },
        )
        block = payload.get("lyric") if isinstance(payload.get("lyric"), dict) else {}
        data = block.get("data") if isinstance(block.get("data"), dict) else {}
        timed = _decode_qq_text(data.get("lyric"))
        translated = _decode_qq_text(data.get("trans"))
        return ProviderLyrics(self.provider, _text(language, 30) or "original", timed, translated or None)


__all__ = ["DirectMusicProvider", "NeteaseProviderAdapter", "QQProviderAdapter"]
