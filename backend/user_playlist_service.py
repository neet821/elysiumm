"""Private playlist operations and safe NetEase source-reference parsing."""

from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import parse_qs, urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import catalog_repository
import models
from catalog_domain import ProviderTrack, TrackAvailability, canonicalize_tracks


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


def _owned_playlist(db: Session, owner_user_id: int, playlist_id: int):
    return (
        db.query(models.UserPlaylist)
        .options(selectinload(models.UserPlaylist.items))
        .filter(
            models.UserPlaylist.id == playlist_id,
            models.UserPlaylist.owner_user_id == owner_user_id,
        )
        .one_or_none()
    )


def get_playlist(db: Session, owner_user_id: int, playlist_id: int):
    return _owned_playlist(db, owner_user_id, playlist_id)


def list_playlists(db: Session, owner_user_id: int) -> list[models.UserPlaylist]:
    return (
        db.query(models.UserPlaylist)
        .options(selectinload(models.UserPlaylist.items))
        .filter(models.UserPlaylist.owner_user_id == owner_user_id)
        .order_by(models.UserPlaylist.updated_at.desc(), models.UserPlaylist.id.desc())
        .all()
    )


def get_imported_playlist(
    db: Session, owner_user_id: int, source_playlist_id: str
) -> models.UserPlaylist | None:
    if not _NETEASE_ID.fullmatch(str(source_playlist_id)):
        return None
    return (
        db.query(models.UserPlaylist)
        .options(selectinload(models.UserPlaylist.items))
        .filter_by(
            owner_user_id=owner_user_id,
            source_provider="netease",
            source_playlist_id=str(source_playlist_id),
        )
        .one_or_none()
    )


def create_playlist(db: Session, owner_user_id: int, name: str):
    normalized_name = str(name or "").strip()
    if not normalized_name or len(normalized_name) > 120:
        raise ValueError("歌单名称不能为空且不能超过 120 个字符")
    row = models.UserPlaylist(owner_user_id=owner_user_id, name=normalized_name)
    db.add(row)
    db.commit()
    return _owned_playlist(db, owner_user_id, row.id)


def rename_playlist(db: Session, owner_user_id: int, playlist_id: int, name: str):
    playlist = _owned_playlist(db, owner_user_id, playlist_id)
    if playlist is None:
        return None
    normalized_name = str(name or "").strip()
    if not normalized_name or len(normalized_name) > 120:
        raise ValueError("歌单名称不能为空且不能超过 120 个字符")
    playlist.name = normalized_name
    playlist.updated_at = datetime.utcnow()
    db.commit()
    return _owned_playlist(db, owner_user_id, playlist_id)


def delete_playlist(db: Session, owner_user_id: int, playlist_id: int) -> bool:
    playlist = _owned_playlist(db, owner_user_id, playlist_id)
    if playlist is None:
        return False
    db.delete(playlist)
    db.commit()
    return True


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


def add_track(
    db: Session, owner_user_id: int, playlist_id: int, track: dict[str, object]
):
    playlist = _owned_playlist(db, owner_user_id, playlist_id)
    if playlist is None:
        return None
    snapshot = _validated_track_snapshot(track)
    canonical_track_id = snapshot.pop("canonical_track_id")
    if canonical_track_id is not None:
        canonical = db.get(models.CanonicalTrack, int(canonical_track_id))
        mapping = catalog_repository.provider_mapping(
            db, str(snapshot["provider"]), str(snapshot["provider_track_id"] or "")
        )
        if (
            canonical is None
            or mapping is None
            or mapping.canonical_track_id != canonical.id
        ):
            raise ValueError("歌曲与曲库编号不匹配")
    position = max((item.position for item in playlist.items), default=-1) + 1
    row = models.UserPlaylistItem(
        playlist_id=playlist.id,
        canonical_track_id=canonical_track_id,
        position=position,
        **snapshot,
    )
    playlist.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_track(
    db: Session, owner_user_id: int, playlist_id: int, item_id: int
) -> bool | None:
    playlist = _owned_playlist(db, owner_user_id, playlist_id)
    if playlist is None:
        return None
    row = next((item for item in playlist.items if item.id == item_id), None)
    if row is None:
        return False
    playlist.items.remove(row)
    db.flush()
    ordered = sorted(playlist.items, key=lambda item: (item.position, item.id))
    temporary_start = (
        max((item.position for item in ordered), default=-1) + len(ordered) + 2
    )
    for offset, item in enumerate(ordered):
        item.position = temporary_start + offset
    db.flush()
    for position, item in enumerate(ordered):
        item.position = position
    playlist.updated_at = datetime.utcnow()
    db.commit()
    return True


def reorder_tracks(
    db: Session,
    owner_user_id: int,
    playlist_id: int,
    ordered_item_ids: list[int],
) -> bool | None:
    playlist = _owned_playlist(db, owner_user_id, playlist_id)
    if playlist is None:
        return None
    current_ids = {item.id for item in playlist.items}
    if (
        len(ordered_item_ids) != len(current_ids)
        or set(ordered_item_ids) != current_ids
    ):
        raise ValueError("排序必须且只能包含该歌单的全部歌曲")
    by_id = {item.id: item for item in playlist.items}
    temporary_start = (
        max((item.position for item in playlist.items), default=-1)
        + len(playlist.items)
        + 2
    )
    for offset, item in enumerate(playlist.items):
        item.position = temporary_start + offset
    db.flush()
    for position, item_id in enumerate(ordered_item_ids):
        by_id[item_id].position = position
    playlist.updated_at = datetime.utcnow()
    db.commit()
    return True


def import_public_playlist(
    db: Session,
    owner_user_id: int,
    source: dict[str, object],
) -> tuple[models.UserPlaylist, bool]:
    """Import a fresh normalized preview as one private, idempotent copy."""

    if source.get("provider") != "netease":
        raise ValueError("暂不支持该平台的歌单导入")
    source_id = str(source.get("source_playlist_id") or "")
    if not _NETEASE_ID.fullmatch(source_id):
        raise ValueError("网易云歌单 ID 无效")
    tracks = source.get("tracks")
    if not isinstance(tracks, list) or len(tracks) > MAX_PLAYLIST_TRACKS:
        raise ValueError("歌单歌曲数量无效或超过上限")
    existing = (
        db.query(models.UserPlaylist)
        .options(selectinload(models.UserPlaylist.items))
        .filter_by(
            owner_user_id=owner_user_id,
            source_provider="netease",
            source_playlist_id=source_id,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    snapshots = [
        _validated_track_snapshot(track) for track in tracks if isinstance(track, dict)
    ]
    if len(snapshots) != len(tracks):
        raise ValueError("网易云歌单包含无效歌曲数据")
    provider_tracks = [
        ProviderTrack(
            provider="netease",
            provider_track_id=snapshot["provider_track_id"],
            title=snapshot["title"],
            artist=snapshot["artist"],
            album=snapshot["album"],
            duration_seconds=snapshot["duration_seconds"],
            artwork_url=snapshot["artwork_url"],
            availability=TrackAvailability(snapshot["availability"]),
        )
        for snapshot in snapshots
        if snapshot["provider_track_id"] is not None
    ]
    playlist = models.UserPlaylist(
        owner_user_id=owner_user_id,
        name=str(source.get("name") or "网易云导入歌单").strip()[:120]
        or "网易云导入歌单",
        source_provider="netease",
        source_playlist_id=source_id,
        source_url=f"https://music.163.com/playlist?id={source_id}",
    )
    db.add(playlist)
    try:
        db.flush()
        canonical_groups = (
            canonicalize_tracks(provider_tracks) if provider_tracks else []
        )
        catalog_repository.upsert_canonical_groups(db, canonical_groups, commit=False)
        canonical_by_provider_id = {
            str(snapshot["provider_track_id"]): mapping.canonical_track_id
            for snapshot in snapshots
            if snapshot["provider_track_id"] is not None
            and (
                mapping := catalog_repository.provider_mapping(
                    db, "netease", str(snapshot["provider_track_id"])
                )
            )
            is not None
        }
        for position, snapshot in enumerate(snapshots):
            db.add(
                models.UserPlaylistItem(
                    playlist_id=playlist.id,
                    canonical_track_id=canonical_by_provider_id.get(
                        str(snapshot["provider_track_id"])
                    )
                    if snapshot["provider_track_id"] is not None
                    else None,
                    position=position,
                    **{
                        key: value
                        for key, value in snapshot.items()
                        if key != "canonical_track_id"
                    },
                )
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = (
            db.query(models.UserPlaylist)
            .options(selectinload(models.UserPlaylist.items))
            .filter_by(
                owner_user_id=owner_user_id,
                source_provider="netease",
                source_playlist_id=source_id,
            )
            .one_or_none()
        )
        if winner is None:
            raise
        return winner, False
    except Exception:
        db.rollback()
        raise
    return _owned_playlist(db, owner_user_id, playlist.id), True


def playlist_payload(playlist: models.UserPlaylist) -> dict[str, object]:
    items = sorted(playlist.items, key=lambda item: (item.position, item.id))
    return {
        "id": playlist.id,
        "name": playlist.name,
        "source": {
            "provider": playlist.source_provider,
            "playlist_id": playlist.source_playlist_id,
            "url": playlist.source_url,
        }
        if playlist.source_provider
        else None,
        "tracks": [
            {
                "id": item.id,
                "canonical_track_id": item.canonical_track_id,
                "provider": item.provider,
                "provider_track_id": item.provider_track_id,
                "title": item.title,
                "artist": item.artist,
                "album": item.album,
                "artwork_url": catalog_repository.safe_artwork_url(item.artwork_url),
                "duration_seconds": item.duration_seconds,
                "availability": item.availability,
                "position": item.position,
            }
            for item in items
        ],
        "created_at": playlist.created_at.isoformat() if playlist.created_at else None,
        "updated_at": playlist.updated_at.isoformat() if playlist.updated_at else None,
    }
