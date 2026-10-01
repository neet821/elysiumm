import hmac
import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import live_stream_service
import models
import schemas
from config import config
from database import get_db
from live_recording_service import UnsafeRecordingPath, index_completed_recording


router = APIRouter(tags=["live"])


def require_loopback(request: Request) -> None:
    host = request.client.host if request.client is not None else ""
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise HTTPException(403, "仅允许本机媒体服务调用")
    except ValueError as exc:
        raise HTTPException(403, "仅允许本机媒体服务调用") from exc


@router.post(
    "/api/internal/live/mediamtx-auth",
    dependencies=[Depends(require_loopback)],
    include_in_schema=False,
)
def mediamtx_auth(
    payload: schemas.MediaMtxAuthRequest,
    db: Session = Depends(get_db),
):
    if payload.action in {"read", "playback"}:
        return {"allowed": True}
    if payload.action != "publish" or payload.path != "live/stream":
        raise HTTPException(403, "媒体操作不允许")
    credential = (
        db.query(models.LiveCredential)
        .filter(models.LiveCredential.kind == "publish")
        .first()
    )
    presented_secret = payload.token or payload.password
    if credential is None or not presented_secret:
        raise HTTPException(403, "推流凭证无效")
    digest = live_stream_service.token_digest(presented_secret)
    if not hmac.compare_digest(credential.token_hash, digest):
        raise HTTPException(403, "推流凭证无效")
    return {"allowed": True}


@router.post(
    "/api/internal/live/recording-complete",
    dependencies=[Depends(require_loopback)],
    include_in_schema=False,
    status_code=201,
)
def recording_complete(
    payload: schemas.LiveRecordingCompleteRequest,
    db: Session = Depends(get_db),
):
    live_session = (
        db.query(models.LiveSession)
        .order_by(models.LiveSession.started_at.desc(), models.LiveSession.id.desc())
        .first()
    )
    if live_session is None:
        raise HTTPException(409, "没有可关联的直播场次")
    try:
        recording = index_completed_recording(
            db,
            recording_root=config.LIVE_RECORDING_ROOT,
            absolute_path=payload.absolute_path,
            live_session_id=live_session.id,
            duration_seconds=payload.duration_seconds,
        )
    except UnsafeRecordingPath as exc:
        raise HTTPException(400, "录像文件不在受管目录") from exc
    return {"recording_id": recording.id, "status": recording.status}
