import asyncio
import logging
from datetime import datetime, timedelta

import models
from config import config
from database import SessionLocal
from live_media_client import MediaMtxClient, MediaPathStatus
from live_recording_policy import apply_recording_policy
from live_stream_service import get_or_create_setting, purge_viewer_history


logger = logging.getLogger("backend.live")
_task: asyncio.Task | None = None


def reconcile_live_state(
    db,
    media_status: MediaPathStatus,
    now: datetime | None = None,
) -> models.LiveSession | None:
    current_time = now or datetime.utcnow()
    active = (
        db.query(models.LiveSession)
        .filter(models.LiveSession.status == "live")
        .order_by(models.LiveSession.started_at.desc())
        .first()
    )

    if media_status.online:
        setting = get_or_create_setting(db)
        if active is None:
            active = models.LiveSession(
                title=setting.title,
                description=setting.description,
                cover_url=setting.cover_url,
                access_mode=setting.access_mode,
                status="live",
                started_at=current_time,
            )
            db.add(active)
        active.publisher_last_seen_at = current_time
        active.width = media_status.width
        active.height = media_status.height
        active.frame_rate = media_status.frame_rate
        active.bit_rate = media_status.bit_rate
        active.video_codec = media_status.video_codec
        active.audio_codec = media_status.audio_codec
        active.error_summary = None
        db.commit()
        db.refresh(active)
        return active

    if active is None:
        return None

    last_seen = active.publisher_last_seen_at or active.started_at
    grace = timedelta(seconds=max(0, config.LIVE_OFFLINE_GRACE_SECONDS))
    if current_time - last_seen >= grace:
        active.status = "ended"
        active.ended_at = current_time
        db.commit()
        db.refresh(active)
    return active


def run_live_reconcile_once() -> None:
    db = SessionLocal()
    try:
        current_time = datetime.utcnow()
        client = MediaMtxClient(config.LIVE_MEDIAMTX_API_URL)
        status = client.path_status()
        reconcile_live_state(db, status, current_time)
        removed_viewers = purge_viewer_history(
            db,
            before=current_time - timedelta(
                days=max(1, config.LIVE_VIEWER_RETENTION_DAYS)
            ),
        )
        if removed_viewers:
            db.commit()
        apply_recording_policy(db, client)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def run_live_reconcile_task() -> None:
    while True:
        try:
            await asyncio.to_thread(run_live_reconcile_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("直播状态对齐暂时失败: %s", type(exc).__name__)
        await asyncio.sleep(5)


def start_live_reconcile_task() -> asyncio.Task:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(run_live_reconcile_task())
    return _task
