from __future__ import annotations

import base64
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

_SAFE_TRACK_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
_QQ_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://y.qq.com/",
    "User-Agent": _USER_AGENT,
}


_QQ_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://y.qq.com/",
    "User-Agent": _USER_AGENT,
}


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
    approved_audio_hosts = frozenset({
        "stream.qqmusic.qq.com",
        "*.stream.qqmusic.qq.com",
    })
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
