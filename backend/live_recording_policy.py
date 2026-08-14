import logging
from pathlib import Path

from sqlalchemy.orm import Session

from config import config
from live_media_client import MediaMtxClient
from live_recording_service import has_recording_capacity
from live_stream_service import get_or_create_setting


logger = logging.getLogger("backend.live")


def apply_recording_policy(
    db: Session,
    client: MediaMtxClient | None = None,
) -> bool:
    setting = get_or_create_setting(db)
    recording_root = Path(config.LIVE_RECORDING_ROOT)
    recording_root.mkdir(parents=True, exist_ok=True)
    capacity = has_recording_capacity(
        recording_root,
        config.LIVE_DISK_RESERVE_BYTES,
    )
    effective = bool(setting.recording_enabled and capacity)
    media_client = client or MediaMtxClient(config.LIVE_MEDIAMTX_API_URL)
    if media_client.recording_enabled() != effective:
        media_client.set_recording_enabled(effective)
    if setting.recording_enabled and not capacity:
        logger.warning("直播录像已因磁盘保留线暂停")
    return effective
