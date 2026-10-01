"""Authentication and access rules shared by public live-viewer endpoints."""

from datetime import datetime, timedelta
import ipaddress

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

import crud
import live_stream_service
import models
import security
from config import config
from database import get_db


optional_bearer = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)
LIVE_COOKIE_NAME = "blue_live_session"
MEDIA_URL = "/live-media/live/stream/index.m3u8"


def optional_current_user(
    bearer: str | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> models.User | None:
    if not bearer:
        return None
    username = security.decode_access_token(bearer)
    user = crud.get_user_by_username(db, username=username)
    if user is None:
        raise HTTPException(401, "登录凭据无效")
    if not user.is_active:
        raise HTTPException(403, "账户已停用")
    return user


def _active_live_session(db: Session) -> models.LiveSession | None:
    return (
        db.query(models.LiveSession)
        .filter(models.LiveSession.status == "live")
        .order_by(models.LiveSession.started_at.desc(), models.LiveSession.id.desc())
        .first()
    )


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client is not None else ""
    try:
        peer_is_loopback = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        peer_is_loopback = False
    forwarded = request.headers.get("x-real-ip", "").strip()
    if peer_is_loopback and forwarded:
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return peer[:45] or "0.0.0.0"


def _signed_live_cookie(viewer: models.LiveViewerSession) -> str:
    return security.create_token(
        {
            "sub": viewer.id,
            "viewer_session_id": viewer.id,
            "live_session_id": viewer.live_session_id,
        },
        timedelta(seconds=config.LIVE_SESSION_TTL_SECONDS),
        token_type="live_view",
    )


def _set_live_cookie(response: Response, viewer: models.LiveViewerSession) -> None:
    response.set_cookie(
        LIVE_COOKIE_NAME,
        _signed_live_cookie(viewer),
        max_age=config.LIVE_SESSION_TTL_SECONDS,
        httponly=True,
        secure=config.LIVE_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _viewer_from_cookie(
    db: Session,
    signed_cookie: str | None,
) -> models.LiveViewerSession:
    if not signed_cookie:
        raise HTTPException(401, "需要观看授权")
    payload = security.decode_token_payload(signed_cookie)
    if payload.get("type") != "live_view":
        raise HTTPException(401, "观看授权无效")
    viewer_id = payload.get("viewer_session_id")
    live_session_id = payload.get("live_session_id")
    if not isinstance(viewer_id, str) or not isinstance(live_session_id, int):
        raise HTTPException(401, "观看授权无效")
    viewer = db.get(models.LiveViewerSession, viewer_id)
    if (
        viewer is None
        or viewer.live_session_id != live_session_id
        or viewer.ended_at is not None
    ):
        raise HTTPException(401, "观看授权已失效")
    return viewer


def _authorize_existing_viewer(
    db: Session,
    viewer: models.LiveViewerSession,
    *,
    now: datetime,
) -> None:
    session = db.get(models.LiveSession, viewer.live_session_id)
    if session is None or session.status != "live":
        raise HTTPException(409, "直播已经结束")
    setting = live_stream_service.get_or_create_setting(db)
    if not setting.viewing_enabled:
        raise HTTPException(403, "直播观看已暂停")
    user = db.get(models.User, viewer.user_id) if viewer.user_id else None
    if user is not None and user.is_active and user.role == "admin":
        return
    if setting.access_mode == "public":
        return
    if setting.access_mode == "allowlist":
        if user is None or not user.is_active:
            raise HTTPException(403, "你没有观看权限")
        allowed = (
            db.query(models.LiveAllowedUser)
            .filter(models.LiveAllowedUser.user_id == user.id)
            .first()
        )
        if allowed is None:
            raise HTTPException(403, "你没有观看权限")
        return
    if setting.access_mode == "invite":
        invite = db.get(models.LiveInvite, viewer.invite_id) if viewer.invite_id else None
        if (
            invite is None
            or invite.revoked_at is not None
            or (invite.expires_at is not None and invite.expires_at <= now)
        ):
            raise HTTPException(403, "邀请链接已失效")
        return
    raise HTTPException(403, "你没有观看权限")
