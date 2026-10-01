from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from admin_audit import add_admin_audit
from config import config
from database import get_db
from live_media_client import MediaMtxClient, MediaServiceUnavailable
from live_stream_service import purge_viewer_history
from routers.live_admin_common import _rate_limit, active_administrator


router = APIRouter()


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
            .outerjoin(models.User, models.User.id == models.LiveViewerSession.user_id)
            .filter(
                models.LiveViewerSession.live_session_id == active.id,
                models.LiveViewerSession.ended_at.is_(None),
                models.LiveViewerSession.last_seen_at
                >= datetime.utcnow() - timedelta(seconds=60),
                or_(
                    models.LiveViewerSession.user_id.is_(None),
                    models.User.role != "admin",
                ),
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
    query = db.query(models.LiveViewerSession).outerjoin(
        models.User,
        models.User.id == models.LiveViewerSession.user_id,
    ).filter(
        models.LiveViewerSession.live_session_id == active.id,
        models.LiveViewerSession.ended_at.is_(None),
        models.LiveViewerSession.last_seen_at
        >= datetime.utcnow() - timedelta(seconds=60),
        or_(
            models.LiveViewerSession.user_id.is_(None),
            models.User.role != "admin",
        ),
    )
    viewers = query.order_by(models.LiveViewerSession.last_seen_at.desc()).limit(limit).all()
    return [_viewer_payload(viewer) for viewer in viewers]


@router.get("/audience/history")
def list_audience_history(
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
    query = (
        db.query(models.LiveViewerSession)
        .outerjoin(models.User, models.User.id == models.LiveViewerSession.user_id)
        .filter(
            models.LiveViewerSession.live_session_id == active.id,
            or_(
                models.LiveViewerSession.user_id.is_(None),
                models.User.role != "admin",
            ),
        )
    )
    if session_id is not None:
        query = query.filter(models.LiveViewerSession.live_session_id == session_id)
    viewers = (
        query.order_by(
            models.LiveViewerSession.first_seen_at.desc(),
            models.LiveViewerSession.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return [_viewer_payload(viewer) for viewer in viewers]


@router.delete("/audience/history")
def delete_audience_history(
    session_id: int | None = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    _rate_limit(
        db, admin, "live_audience_history_delete", resource_id=session_id
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


def _viewer_payload(viewer: models.LiveViewerSession) -> dict:
    return {
        "id": viewer.id,
        "live_session_id": viewer.live_session_id,
        "session_title": viewer.session.title if viewer.session else None,
        "session_status": viewer.session.status if viewer.session else None,
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
