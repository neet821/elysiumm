"""Private playlist operations and safe NetEase source-reference parsing."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session, selectinload

import catalog_repository
import models
from user_playlist_import_service import import_public_playlist as import_public_playlist
from user_playlist_queries import get_owned_playlist as _owned_playlist
from user_playlist_validation import (
    MAX_PLAYLIST_TRACKS as MAX_PLAYLIST_TRACKS,
    _NETEASE_ID as _NETEASE_ID,
    _PROVIDERS as _PROVIDERS,
    _validated_track_snapshot as _validated_track_snapshot,
    normalize_netease_playlist_reference as normalize_netease_playlist_reference,
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
