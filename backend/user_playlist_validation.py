"""Input validation shared by private playlist writes and public imports."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import catalog_repository
from catalog_domain import TrackAvailability


_NETEASE_ID = re.compile(r"^[0-9]{1,32}$")
_PROVIDERS = {"netease", "qq", "audius"}
MAX_PLAYLIST_TRACKS = 2000


def normalize_netease_playlist_reference(reference: object) -> str:
    """Accept only a decimal id or an HTTPS music.163.com playlist URL."""

    value = str(reference or "").strip()
    if _NETEASE_ID.fullmatch(value):
        return value
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError("请输入网易云公开歌单 ID 或链接")
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise ValueError("网易云歌单链接无效") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "music.163.com"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("仅支持 HTTPS 网易云公开歌单链接")
    query_text = parsed.query
    if parsed.fragment:
        fragment = parsed.fragment.lstrip("/")
        fragment_path, separator, fragment_query = fragment.partition("?")
        if fragment_path not in {"playlist", "playlist/"}:
            raise ValueError("网易云链接不是歌单地址")
        if query_text and fragment_query:
            raise ValueError("网易云歌单链接参数无效")
        query_text = fragment_query if separator else query_text
    elif parsed.path.rstrip("/") != "/playlist":
        raise ValueError("网易云链接不是歌单地址")
    query = parse_qs(query_text, keep_blank_values=True, strict_parsing=True)
    if set(query) != {"id"} or len(query["id"]) != 1:
        raise ValueError("网易云歌单链接必须只包含歌单 ID")
    playlist_id = query["id"][0]
    if not _NETEASE_ID.fullmatch(playlist_id):
        raise ValueError("网易云歌单 ID 无效")
    return playlist_id


def _validated_track_snapshot(track: dict[str, object]) -> dict[str, object]:
    provider = str(track.get("provider") or "netease").strip().lower()
    provider_track_id = str(track.get("provider_track_id") or "").strip() or None
    title = str(track.get("title") or "").strip()
    artist = str(track.get("artist") or "未知音乐人").strip()
    if provider not in _PROVIDERS:
        raise ValueError("不支持的歌曲来源")
    if not title or len(title) > 300 or len(artist) > 500:
        raise ValueError("歌曲信息无效")
    if provider_track_id is not None and len(provider_track_id) > 120:
        raise ValueError("歌曲编号无效")
    if (
        provider == "netease"
        and provider_track_id
        and not _NETEASE_ID.fullmatch(provider_track_id)
    ):
        raise ValueError("网易云歌曲编号无效")
    try:
        availability = TrackAvailability(
            str(track.get("availability", "unavailable"))
        ).value
    except ValueError as exc:
        raise ValueError("歌曲可用状态无效") from exc
    try:
        duration = int(track.get("duration_seconds") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("歌曲时长无效") from exc
    if duration < 0 or duration > 86400:
        raise ValueError("歌曲时长无效")
    return {
        "provider": provider,
        "provider_track_id": provider_track_id,
        "title": title,
        "artist": artist or "未知音乐人",
        "album": str(track.get("album") or "").strip()[:300] or None,
        "artwork_url": catalog_repository.safe_artwork_url(track.get("artwork_url")),
        "duration_seconds": duration,
        "availability": availability,
        "canonical_track_id": track.get("canonical_track_id"),
    }
