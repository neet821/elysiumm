"""Import normalized public playlist snapshots as private website copies."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import catalog_repository
import models
from catalog_domain import ProviderTrack, TrackAvailability, canonicalize_tracks
from user_playlist_queries import get_owned_playlist
from user_playlist_validation import (
    MAX_PLAYLIST_TRACKS,
    _NETEASE_ID,
    _validated_track_snapshot,
)


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
    return get_owned_playlist(db, owner_user_id, playlist.id), True
