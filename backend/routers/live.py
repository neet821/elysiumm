from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import live_stream_service
import models
import schemas
from config import config as config
from database import get_db
from live_viewer_service import (
    LIVE_COOKIE_NAME as LIVE_COOKIE_NAME,
    MEDIA_URL as MEDIA_URL,
    _active_live_session as _active_live_session,
    _authorize_existing_viewer as _authorize_existing_viewer,
    _client_ip as _client_ip,
    _set_live_cookie as _set_live_cookie,
    _signed_live_cookie as _signed_live_cookie,
    _viewer_from_cookie as _viewer_from_cookie,
    optional_current_user as optional_current_user,
)
from routers.live_internal import (
    mediamtx_auth as mediamtx_auth,
    recording_complete as recording_complete,
    require_loopback as require_loopback,
    router as internal_router,
)
from routers import live_viewer_routes


router = APIRouter(tags=["live"])
MESSAGE_RATE_LIMIT_WINDOW_SECONDS = 5
MESSAGE_RATE_LIMIT_COUNT = 3


@router.get("/api/live/status", response_model=schemas.LiveStatusResponse)
def live_status(db: Session = Depends(get_db)):
    setting = live_stream_service.get_or_create_setting(db)
    session = _active_live_session(db)
    latest_completed = None
    if session is None:
        latest_completed = (
            db.query(models.LiveSession)
            .filter(models.LiveSession.status == "ended")
            .order_by(
                models.LiveSession.ended_at.desc(),
                models.LiveSession.id.desc(),
            )
            .first()
        )
    return {
        "status": (
            "live"
            if session is not None
            else "ended"
            if latest_completed is not None
            else "waiting"
        ),
        "title": setting.title,
        "description": setting.description,
        "cover_url": setting.cover_url,
        "access_mode": setting.access_mode,
        "stream_quality": setting.stream_quality,
        "target_bitrate_kbps": setting.target_bitrate_kbps,
        "latency_mode": setting.latency_mode,
        "started_at": (
            session.started_at
            if session is not None
            else latest_completed.started_at
            if latest_completed is not None
            else None
        ),
    }


def _message_payload(message: models.LiveMessage) -> dict:
    return {
        "id": message.id,
        "live_session_id": message.live_session_id,
        "viewer_session_id": message.viewer_session_id,
        "nickname": message.nickname,
        "content": message.content,
        "created_at": message.created_at,
    }


@router.get("/api/live/messages")
def list_live_messages(
    limit: int = Query(80, ge=1, le=200),
    blue_live_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    viewer = _viewer_from_cookie(db, blue_live_session)
    _authorize_existing_viewer(db, viewer, now=datetime.utcnow())
    rows = (
        db.query(models.LiveMessage)
        .filter(models.LiveMessage.live_session_id == viewer.live_session_id)
        .order_by(models.LiveMessage.id.desc())
        .limit(limit)
        .all()
    )
    return [_message_payload(row) for row in reversed(rows)]


@router.post("/api/live/messages", status_code=status.HTTP_201_CREATED)
def create_live_message(
    payload: schemas.LiveMessageCreateRequest,
    blue_live_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    viewer = _viewer_from_cookie(db, blue_live_session)
    _authorize_existing_viewer(db, viewer, now=now)
    recent_count = (
        db.query(func.count(models.LiveMessage.id))
        .filter(
            models.LiveMessage.viewer_session_id == viewer.id,
            models.LiveMessage.created_at
            >= now - timedelta(seconds=MESSAGE_RATE_LIMIT_WINDOW_SECONDS),
        )
        .scalar()
        or 0
    )
    if recent_count >= MESSAGE_RATE_LIMIT_COUNT:
        raise HTTPException(429, "发送过快，请稍后再试")
    message = models.LiveMessage(
        live_session_id=viewer.live_session_id,
        viewer_session_id=viewer.id,
        nickname=payload.nickname,
        content=payload.content,
        created_at=now,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return _message_payload(message)


create_live_viewer_session = live_viewer_routes.create_live_viewer_session
live_viewer_heartbeat = live_viewer_routes.live_viewer_heartbeat
end_live_viewer_session = live_viewer_routes.end_live_viewer_session
authorize_live_media = live_viewer_routes.authorize_live_media

router.include_router(live_viewer_routes.router)
router.include_router(internal_router)
