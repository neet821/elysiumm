"""HTTP endpoints for live viewer sessions and media authorization."""

from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

import live_stream_service
import live_viewer_service as viewer_service
import models
import schemas
from config import config
from database import get_db


router = APIRouter(tags=["live"])


@router.post(
    "/api/live/session",
    response_model=schemas.LiveViewerSessionResponse,
    status_code=201,
)
def create_live_viewer_session(
    payload: schemas.LiveSessionCreateRequest,
    request: Request,
    response: Response,
    user: models.User | None = Depends(viewer_service.optional_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    live_session = viewer_service._active_live_session(db)
    if live_session is None:
        raise HTTPException(409, "直播尚未开始")
    decision = live_stream_service.authorize_viewer(
        db,
        user=user,
        invite_token=payload.invite_token,
        now=now,
    )
    if not decision.allowed:
        code = 401 if decision.reason == "login_required" else 403
        messages = {
            "login_required": "需要登录后观看",
            "invite_invalid": "邀请链接已失效",
            "viewing_disabled": "直播观看已暂停",
        }
        raise HTTPException(code, messages.get(decision.reason, "你没有观看权限"))
    viewer = live_stream_service.open_viewer_session(
        db,
        live_session=live_session,
        decision=decision,
        client_ip=viewer_service._client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        now=now,
    )
    db.commit()
    db.refresh(viewer)
    viewer_service._set_live_cookie(response, viewer)
    return {
        "viewer_session_id": viewer.id,
        "live_session_id": viewer.live_session_id,
        "media_url": viewer_service.MEDIA_URL,
        "expires_in": config.LIVE_SESSION_TTL_SECONDS,
    }


@router.post(
    "/api/live/session/heartbeat",
    response_model=schemas.LiveHeartbeatResponse,
)
def live_viewer_heartbeat(
    response: Response,
    blue_live_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    viewer = viewer_service._viewer_from_cookie(db, blue_live_session)
    viewer_service._authorize_existing_viewer(db, viewer, now=now)
    try:
        viewer = live_stream_service.heartbeat_viewer(db, viewer.id, now)
    except LookupError as exc:
        raise HTTPException(401, "观看授权已失效") from exc
    db.commit()
    db.refresh(viewer)
    viewer_service._set_live_cookie(response, viewer)
    return {
        "viewer_session_id": viewer.id,
        "watched_seconds": viewer.watched_seconds,
        "expires_in": config.LIVE_SESSION_TTL_SECONDS,
    }


@router.post("/api/live/session/end", status_code=204)
def end_live_viewer_session(
    response: Response,
    blue_live_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    viewer = viewer_service._viewer_from_cookie(db, blue_live_session)
    try:
        live_stream_service.end_viewer_session(db, viewer.id, datetime.utcnow())
    except LookupError as exc:
        raise HTTPException(401, "观看授权已失效") from exc
    db.commit()
    response.delete_cookie(viewer_service.LIVE_COOKIE_NAME, path="/")
    return response


@router.get("/api/live/authorize-media", status_code=204)
def authorize_live_media(
    blue_live_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    viewer = viewer_service._viewer_from_cookie(db, blue_live_session)
    viewer_service._authorize_existing_viewer(db, viewer, now=datetime.utcnow())
    return Response(status_code=204)
