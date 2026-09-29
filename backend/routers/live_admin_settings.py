from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
from admin_audit import add_admin_audit
from config import config
from database import get_db
from live_media_client import MediaServiceUnavailable
from live_recording_policy import apply_recording_policy
from live_stream_service import get_or_create_setting
from routers.live_admin_common import active_administrator


router = APIRouter()
logger = logging.getLogger("backend.live")


def _setting_payload(db: Session, setting: models.LiveSetting) -> dict:
    credential = (
        db.query(models.LiveCredential)
        .filter(models.LiveCredential.kind == "publish")
        .one_or_none()
    )
    return {
        "id": setting.id,
        "title": setting.title,
        "description": setting.description,
        "cover_url": setting.cover_url,
        "access_mode": setting.access_mode,
        "viewing_enabled": setting.viewing_enabled,
        "recording_enabled": setting.recording_enabled,
        "stream_quality": setting.stream_quality,
        "target_bitrate_kbps": setting.target_bitrate_kbps,
        "latency_mode": setting.latency_mode,
        "revision": setting.revision,
        "updated_at": setting.updated_at,
        "stream_key_hint": credential.token_hint if credential else None,
        "rtmp_server": config.LIVE_RTMP_PUBLIC_URL,
        "obs_stream_key_format": "stream?token=••••••",
    }


@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    setting = get_or_create_setting(db)
    db.commit()
    db.refresh(setting)
    return _setting_payload(db, setting)


@router.put("/settings")
def update_settings(
    payload: schemas.LiveAdminSettingsUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    setting = get_or_create_setting(db)
    provided_fields = payload.model_fields_set
    stream_quality = (
        payload.stream_quality
        if "stream_quality" in provided_fields and payload.stream_quality is not None
        else setting.stream_quality
    )
    target_bitrate_kbps = (
        payload.target_bitrate_kbps
        if "target_bitrate_kbps" in provided_fields
        else setting.target_bitrate_kbps
    )
    latency_mode = (
        payload.latency_mode
        if "latency_mode" in provided_fields and payload.latency_mode is not None
        else setting.latency_mode
    )
    changed = (
        db.query(models.LiveSetting)
        .filter(
            models.LiveSetting.id == setting.id,
            models.LiveSetting.revision == payload.revision,
        )
        .update(
            {
                models.LiveSetting.title: payload.title.strip(),
                models.LiveSetting.description: payload.description.strip(),
                models.LiveSetting.cover_url: (
                    payload.cover_url.strip() if payload.cover_url else None
                ),
                models.LiveSetting.access_mode: payload.access_mode,
                models.LiveSetting.viewing_enabled: payload.viewing_enabled,
                models.LiveSetting.recording_enabled: payload.recording_enabled,
                models.LiveSetting.stream_quality: stream_quality,
                models.LiveSetting.target_bitrate_kbps: target_bitrate_kbps,
                models.LiveSetting.latency_mode: latency_mode,
                models.LiveSetting.revision: payload.revision + 1,
                models.LiveSetting.updated_by: admin.id,
                models.LiveSetting.updated_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    if changed != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "设置已被其他操作更新")
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_settings_update",
        resource_type="live_setting",
        resource_id=setting.id,
        detail=(
            f"mode={payload.access_mode}; "
            f"viewing_enabled={payload.viewing_enabled}; "
            f"recording_enabled={payload.recording_enabled}; "
            f"quality={stream_quality}; "
            f"bitrate={target_bitrate_kbps}; "
            f"latency={latency_mode}"
        ),
    )
    db.commit()
    db.refresh(setting)
    try:
        apply_recording_policy(db)
    except MediaServiceUnavailable:
        logger.warning("直播自动录制设置将在媒体服务恢复后重试")
    return _setting_payload(db, setting)
