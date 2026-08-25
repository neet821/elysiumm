from datetime import datetime, timedelta
import logging
from pathlib import Path
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
import schemas
from admin_audit import add_admin_audit
from api_rate_limit import enforce_user_rate_limit
from config import config
from database import get_db
from dependencies import get_current_user
from live_media_client import MediaMtxClient, MediaServiceUnavailable
from live_recording_policy import apply_recording_policy
from live_recording_service import (
    UnsafeRecordingPath,
    delete_recording,
    resolve_recording_path,
)
from live_stream_service import (
    generate_secret,
    get_or_create_setting,
    purge_viewer_history,
)


router = APIRouter(prefix="/api/admin/live", tags=["live-admin"])
logger = logging.getLogger("backend.live")
MUTATION_LIMIT = 10
MUTATION_WINDOW_SECONDS = 60


def active_administrator(
    user: models.User = Depends(get_current_user),
) -> models.User:
    if user.role != "admin" or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


def _rate_limit(
    db: Session,
    admin: models.User,
    action: str,
    *,
    resource_id: str | int | None = None,
) -> None:
    enforce_user_rate_limit(
        db,
        actor_id=admin.id,
        action=action,
        limit=MUTATION_LIMIT,
        window_seconds=MUTATION_WINDOW_SECONDS,
        audit_action=action,
        resource_type="live_stream",
        resource_id=resource_id,
    )


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


def _allowed_payload(row: models.LiveAllowedUser) -> dict:
    return {
        "user_id": row.user_id,
        "username": row.user.username,
        "email": row.user.email,
        "created_at": row.created_at,
    }


def _invite_payload(invite: models.LiveInvite) -> dict:
    now = datetime.utcnow()
    if invite.revoked_at is not None:
        invite_status = "revoked"
    elif invite.expires_at is not None and invite.expires_at <= now:
        invite_status = "expired"
    else:
        invite_status = "active"
    return {
        "id": invite.id,
        "token_hint": invite.token_hint,
        "status": invite_status,
        "expires_at": invite.expires_at,
        "last_used_at": invite.last_used_at,
        "created_at": invite.created_at,
    }


def _active_invite_query(db: Session):
    now = datetime.utcnow()
    return db.query(models.LiveInvite).filter(
        models.LiveInvite.revoked_at.is_(None),
        or_(
            models.LiveInvite.expires_at.is_(None),
            models.LiveInvite.expires_at > now,
        ),
    )


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
    next_revision = payload.revision + 1
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
                models.LiveSetting.revision: next_revision,
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


@router.get("/allowed-users")
def list_allowed_users(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    rows = (
        db.query(models.LiveAllowedUser)
        .join(models.User, models.User.id == models.LiveAllowedUser.user_id)
        .order_by(models.User.username.asc())
        .all()
    )
    return [_allowed_payload(row) for row in rows]


@router.put("/allowed-users")
def replace_allowed_users(
    payload: schemas.LiveAllowedUsersUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    user_ids = sorted(set(payload.user_ids))
    users = (
        db.query(models.User)
        .filter(models.User.id.in_(user_ids), models.User.is_active.is_(True))
        .all()
        if user_ids
        else []
    )
    if len(users) != len(user_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "指定用户不存在或已停用",
        )
    db.query(models.LiveAllowedUser).delete(synchronize_session=False)
    db.add_all(
        models.LiveAllowedUser(user_id=user.id, added_by=admin.id)
        for user in users
    )
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_allowed_users_update",
        resource_type="live_allowed_user",
        detail=f"count={len(users)}",
    )
    db.commit()
    return list_allowed_users(db=db, _admin=admin)


@router.post("/stream-key/rotate", status_code=status.HTTP_201_CREATED)
def rotate_stream_key(
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    _rate_limit(db, admin, "live_stream_key_rotate")
    raw, digest, hint = generate_secret()
    credential = (
        db.query(models.LiveCredential)
        .filter(models.LiveCredential.kind == "publish")
        .one_or_none()
    )
    if credential is None:
        credential = models.LiveCredential(
            kind="publish",
            token_hash=digest,
            token_hint=hint,
        )
        db.add(credential)
    else:
        credential.token_hash = digest
        credential.token_hint = hint
    credential.rotated_at = datetime.utcnow()
    credential.created_by = admin.id
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_stream_key_rotate",
        resource_type="live_credential",
        outcome="success",
        detail=f"hint={hint}",
    )
    db.commit()
    return {
        "stream_key": raw,
        "obs_stream_key": f"stream?token={raw}",
        "stream_key_hint": hint,
        "rtmp_server": config.LIVE_RTMP_PUBLIC_URL,
    }


@router.get("/invites")
def list_invites(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    rows = _active_invite_query(db).order_by(models.LiveInvite.created_at.desc()).limit(1).all()
    return [_invite_payload(invite) for invite in rows]


@router.post("/invites", status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: schemas.LiveInviteCreateRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    _rate_limit(db, admin, "live_invite_create")
    if _active_invite_query(db).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "已有有效邀请链接，请先停用后再生成")
    raw, digest, hint = generate_secret()
    invite = models.LiveInvite(
        token_hash=digest,
        token_hint=hint,
        expires_at=(
            datetime.utcnow() + timedelta(hours=payload.expires_in_hours)
            if payload.expires_in_hours is not None
            else None
        ),
        created_by=admin.id,
    )
    db.add(invite)
    db.flush()
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_invite_create",
        resource_type="live_invite",
        resource_id=invite.id,
        detail=f"hint={hint}",
    )
    db.commit()
    db.refresh(invite)
    result = _invite_payload(invite)
    result.update(
        {
            "invite_token": raw,
            "invite_url": (
                f"{config.LIVE_PUBLIC_BASE_URL}/live?invite={quote(raw)}"
            ),
        }
    )
    return result


@router.post("/invites/{invite_id}/revoke")
def revoke_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    invite = db.get(models.LiveInvite, invite_id)
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "邀请不存在")
    if invite.revoked_at is None:
        invite.revoked_at = datetime.utcnow()
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_invite_revoke",
        resource_type="live_invite",
        resource_id=invite.id,
        detail=f"hint={invite.token_hint}",
    )
    db.commit()
    db.refresh(invite)
    return _invite_payload(invite)


@router.get("/status")
def live_status(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    active = (
        db.query(models.LiveSession)
        .filter(models.LiveSession.status == "live")
        .order_by(models.LiveSession.started_at.desc())
        .first()
    )
    active_viewers = 0
    if active is not None:
        active_viewers = (
            db.query(func.count(models.LiveViewerSession.id))
            .filter(
                models.LiveViewerSession.live_session_id == active.id,
                models.LiveViewerSession.ended_at.is_(None),
                models.LiveViewerSession.last_seen_at
                >= datetime.utcnow() - timedelta(seconds=60),
            )
            .scalar()
            or 0
        )
    return {
        "is_live": active is not None,
        "active_viewers": int(active_viewers),
        "session": _session_payload(active) if active else None,
    }


@router.post("/kick-publisher")
def kick_publisher(
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    _rate_limit(db, admin, "live_kick_publisher")
    try:
        MediaMtxClient(config.LIVE_MEDIAMTX_API_URL).kick_publisher()
    except MediaServiceUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "直播服务暂时不可用",
        ) from exc
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_kick_publisher",
        resource_type="live_stream",
        outcome="success",
        detail="publisher disconnected",
    )
    db.commit()
    return {"status": "disconnected"}


@router.get("/audience")
def list_audience(
    session_id: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    active = (
        db.query(models.LiveSession)
        .filter(models.LiveSession.status == "live")
        .order_by(models.LiveSession.started_at.desc())
        .first()
    )
    if active is None or (session_id is not None and session_id != active.id):
        return []
    query = db.query(models.LiveViewerSession).filter(
        models.LiveViewerSession.live_session_id == active.id,
        models.LiveViewerSession.ended_at.is_(None),
        models.LiveViewerSession.last_seen_at
        >= datetime.utcnow() - timedelta(seconds=60),
    )
    viewers = (
        query.order_by(models.LiveViewerSession.last_seen_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": viewer.id,
            "live_session_id": viewer.live_session_id,
            "user_id": viewer.user_id,
            "username": viewer.user.username if viewer.user else None,
            "email": viewer.user.email if viewer.user else None,
            "invite_id": viewer.invite_id,
            "ip_address": viewer.ip_address,
            "country": viewer.country,
            "region": viewer.region,
            "city": viewer.city,
            "device_type": viewer.device_type,
            "operating_system": viewer.operating_system,
            "browser": viewer.browser,
            "first_seen_at": viewer.first_seen_at,
            "last_seen_at": viewer.last_seen_at,
            "watched_seconds": viewer.watched_seconds,
            "ended_at": viewer.ended_at,
        }
        for viewer in viewers
    ]


@router.delete("/audience/history")
def delete_audience_history(
    session_id: int | None = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    _rate_limit(
        db,
        admin,
        "live_audience_history_delete",
        resource_id=session_id,
    )
    removed = purge_viewer_history(
        db,
        before=datetime.utcnow() + timedelta(seconds=1),
        live_session_id=session_id,
    )
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_audience_history_delete",
        resource_type="live_viewer_session",
        resource_id=session_id,
        detail=f"deleted={removed}",
    )
    db.commit()
    return {"deleted": removed}


def _session_payload(session: models.LiveSession) -> dict:
    return {
        "id": session.id,
        "title": session.title,
        "access_mode": session.access_mode,
        "status": session.status,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "width": session.width,
        "height": session.height,
        "frame_rate": session.frame_rate,
        "bit_rate": session.bit_rate,
        "video_codec": session.video_codec,
        "audio_codec": session.audio_codec,
        "error_summary": session.error_summary,
    }


@router.get("/sessions")
def list_sessions(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    rows = (
        db.query(models.LiveSession)
        .order_by(models.LiveSession.started_at.desc())
        .limit(limit)
        .all()
    )
    return [_session_payload(row) for row in rows]


def _recording_payload(recording: models.LiveRecording) -> dict:
    return {
        "id": recording.id,
        "session_id": recording.session_id,
        "display_name": recording.display_name,
        "file_size": recording.file_size,
        "duration_seconds": recording.duration_seconds,
        "sha256": recording.sha256,
        "status": recording.status,
        "created_at": recording.created_at,
        "ready_at": recording.ready_at,
        "remote_provider": recording.remote_provider,
        "remote_file_id": recording.remote_file_id,
        "download_url": f"/api/admin/live/recordings/{recording.id}/download",
    }


@router.get("/recordings")
def list_recordings(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    rows = (
        db.query(models.LiveRecording)
        .order_by(models.LiveRecording.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_recording_payload(row) for row in rows]


def _get_recording(db: Session, recording_id: int) -> models.LiveRecording:
    recording = db.get(models.LiveRecording, recording_id)
    if recording is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "录像不存在")
    return recording


@router.get("/recordings/{recording_id}/download")
def download_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    recording = _get_recording(db, recording_id)
    try:
        path = resolve_recording_path(
            config.LIVE_RECORDING_ROOT,
            recording.relative_path,
        )
    except (UnsafeRecordingPath, FileNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "录像文件不存在") from exc
    filename = re.sub(r"[^A-Za-z0-9._ -]+", "_", recording.display_name).strip()
    return FileResponse(path, filename=filename or f"recording-{recording.id}.mp4")


@router.put("/recordings/{recording_id}")
def update_recording(
    recording_id: int,
    payload: schemas.LiveRecordingUpdateRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    recording = _get_recording(db, recording_id)
    recording.display_name = payload.display_name.strip()
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_recording_update",
        resource_type="live_recording",
        resource_id=recording.id,
        detail="display name updated",
    )
    db.commit()
    db.refresh(recording)
    return _recording_payload(recording)


@router.delete("/recordings/{recording_id}")
def remove_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    _rate_limit(
        db,
        admin,
        "live_recording_delete",
        resource_id=recording_id,
    )
    recording = _get_recording(db, recording_id)
    if recording.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "录像仍在处理中")
    try:
        deleted = delete_recording(
            db,
            recording=recording,
            recording_root=Path(config.LIVE_RECORDING_ROOT),
        )
    except UnsafeRecordingPath as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "录像路径无效") from exc
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_recording_delete",
        resource_type="live_recording",
        resource_id=recording_id,
        outcome="success" if deleted else "missing",
        detail=f"file_deleted={deleted}",
    )
    db.commit()
    return {"deleted": deleted}
