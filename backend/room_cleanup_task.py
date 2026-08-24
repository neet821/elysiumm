"""
房间自动清理任务
- 无人 10 分钟后标记为过期
- 过期 30 分钟后软删除，保留记录便于排查
"""
import os
import asyncio
import shutil
from pathlib import Path
from sqlalchemy.orm import Session
from database import SessionLocal
import sync_room_crud
import game_service
import models
import transfer_service
import logging
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads/sync_room_videos"
MUSIC_UPLOAD_ROOT = config.UPLOAD_DIR / "music_rooms"
VIDEO_UPLOAD_ROOT = config.PRIVATE_STORAGE_DIR / "video_rooms"
VIDEO_SUBTITLE_ROOT = config.PRIVATE_STORAGE_DIR / "video_subtitles"
IDLE_TIMEOUT_MINUTES = 10
DELETE_AFTER_EXPIRED_MINUTES = 30

def delete_video_file(file_path: str):
    """删除视频文件"""
    if not file_path:
        return

    full_path = os.path.join(UPLOAD_DIR, os.path.basename(file_path))
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
            logger.info(f"✅ 已删除视频文件: {full_path}")
        except Exception as e:
            logger.error(f"❌ 删除文件失败 {full_path}: {e}")

def cleanup_inactive_rooms(db: Session):
    """按统一生命周期规则清理无人房间。"""
    changed_count = sync_room_crud.cleanup_empty_rooms(
        db,
        minutes=IDLE_TIMEOUT_MINUTES,
        delete_after_minutes=DELETE_AFTER_EXPIRED_MINUTES,
    )
    cleanup_music_room_uploads(db)
    cleanup_video_room_uploads(db)
    if changed_count:
        logger.info(f"🎉 房间生命周期清理完成，共更新 {changed_count} 个房间")
    return changed_count


def cleanup_music_room_uploads(db: Session) -> int:
    """Remove only room-owned upload directories allowed by lifecycle policy."""
    root = Path(MUSIC_UPLOAD_ROOT).resolve()
    rooms = db.query(models.SyncRoom).filter(
        models.SyncRoom.mode == "music",
        models.SyncRoom.auto_delete_file.is_(True),
        models.SyncRoom.lifecycle_status.in_(("closed", "expired", "deleted")),
    ).all()
    removed = 0
    for room in rooms:
        room_dir = (root / str(room.id)).resolve()
        if room_dir.parent != root or not room_dir.is_dir():
            continue
        shutil.rmtree(room_dir)
        removed += 1
    return removed


def _remove_managed_file(value, root) -> bool:
    if not value:
        return False
    root = Path(root).resolve()
    candidate = Path(value).expanduser().resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return False
    candidate.unlink()
    return True


def cleanup_video_room_uploads(db: Session) -> int:
    """Remove only managed video-domain files owned by closed rooms."""
    terminal_states = ("closed", "expired", "deleted")
    items = db.query(models.VideoPlaylistItem).join(
        models.SyncRoom,
        models.SyncRoom.id == models.VideoPlaylistItem.room_id,
    ).filter(
        models.SyncRoom.lifecycle_status.in_(terminal_states),
    ).all()
    removed = 0
    for item in items:
        if item.owned_file and _remove_managed_file(item.storage_path, VIDEO_UPLOAD_ROOT):
            removed += 1
        for subtitle in item.subtitles:
            if _remove_managed_file(subtitle.storage_path, VIDEO_SUBTITLE_ROOT):
                removed += 1
    return removed

async def run_cleanup_task():
    """定时运行清理任务"""
    logger.info("🚀 房间清理任务启动")

    while True:
        try:
            db = SessionLocal()
            deleted_count = cleanup_inactive_rooms(db)
            game_count = game_service.cleanup_rooms(db)
            transfer_service.cleanup_expired(db)
            db.close()

            if deleted_count > 0:
                logger.info(f"✅ 本次清理了 {deleted_count} 个房间")
            if game_count > 0:
                logger.info(f"✅ 本次更新了 {game_count} 个桌游房间")

        except Exception as e:
            logger.error(f"❌ 清理任务出错: {e}")

        # 中转链接必须在五分钟过期窗口后不超过三十秒内清理。
        await asyncio.sleep(int(os.getenv("CLEANUP_INTERVAL_SECONDS", "30")))

if __name__ == "__main__":
    # 可以手动运行清理
    db = SessionLocal()
    try:
        count = cleanup_inactive_rooms(db)
        print(f"清理了 {count} 个房间")
    finally:
        db.close()
