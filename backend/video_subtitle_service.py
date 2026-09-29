"""Subtitle persistence and serialization for video playlist items."""

from __future__ import annotations

import models
from video_service_common import _touch_room, ensure_video_session


def select_subtitle(db, room, subtitle) -> models.VideoSession:
    session = ensure_video_session(db, room)
    item = db.get(models.VideoPlaylistItem, subtitle.item_id)
    if not item or item.room_id != room.id or session.current_item_id != item.id:
        raise ValueError("这个字幕不属于当前视频")
    session.selected_subtitle_id = subtitle.id
    _touch_room(room)
    db.commit()
    db.refresh(session)
    return session


def delete_subtitle(db, room, subtitle):
    item = db.get(models.VideoPlaylistItem, subtitle.item_id)
    if not item or item.room_id != room.id:
        raise ValueError("这个字幕属于其他房间")
    session = ensure_video_session(db, room)
    if session.selected_subtitle_id == subtitle.id:
        session.selected_subtitle_id = None
    path = subtitle.storage_path
    db.delete(subtitle)
    _touch_room(room)
    db.commit()
    return path


def create_subtitle_record(
    db,
    item,
    *,
    created_by,
    label,
    language,
    storage_path,
    original_filename,
    file_size,
) -> models.VideoSubtitle:
    if not isinstance(storage_path, str) or not storage_path:
        raise ValueError("字幕存储位置不能为空")
    if not isinstance(file_size, int) or isinstance(file_size, bool) or file_size <= 0:
        raise ValueError("字幕文件大小无效")
    if not isinstance(label, str) or not label.strip() or len(label.strip()) > 80:
        raise ValueError("字幕名称无效")
    if not isinstance(language, str) or not language.strip() or len(language) > 35:
        raise ValueError("字幕语言无效")
    if not isinstance(original_filename, str) or not original_filename:
        raise ValueError("字幕文件名无效")
    subtitle = models.VideoSubtitle(
        item_id=item.id,
        label=label.strip(),
        language=language.strip(),
        format="vtt",
        storage_path=storage_path,
        original_filename=original_filename,
        file_size=file_size,
        created_by=created_by,
    )
    db.add(subtitle)
    db.commit()
    db.refresh(subtitle)
    return subtitle


def _subtitle_payload(subtitle) -> dict:
    return {
        "id": subtitle.id,
        "item_id": subtitle.item_id,
        "label": subtitle.label,
        "language": subtitle.language,
        "format": subtitle.format,
        "original_filename": subtitle.original_filename,
        "file_size": subtitle.file_size,
        "src": f"/api/video/subtitles/{subtitle.id}/stream",
        "created_at": subtitle.created_at.isoformat() if subtitle.created_at else None,
    }
