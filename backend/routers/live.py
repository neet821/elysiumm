from datetime import datetime, timedelta
import hmac
import ipaddress

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func
from sqlalchemy.orm import Session

import crud
import live_stream_service
import models
import schemas
import security
from config import config
from database import get_db
from live_recording_service import UnsafeRecordingPath, index_completed_recording


router = APIRouter(tags=["live"])
optional_bearer = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)
LIVE_COOKIE_NAME = "blue_live_session"
MEDIA_URL = "/live-media/live/stream/index.m3u8"
MESSAGE_RATE_LIMIT_WINDOW_SECONDS = 5
MESSAGE_RATE_LIMIT_COUNT = 3


def require_loopback(request: Request) -> None:
    host = request.client.host if request.client is not None else ""
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise HTTPException(403, "仅允许本机媒体服务调用")
    except ValueError as exc:
        raise HTTPException(403, "仅允许本机媒体服务调用") from exc


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


@router.post(
    "/api/live/session",
    response_model=schemas.LiveViewerSessionResponse,
    status_code=201,
)
def create_live_viewer_session(
    payload: schemas.LiveSessionCreateRequest,
    request: Request,
    response: Response,
    user: models.User | None = Depends(optional_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    live_session = _active_live_session(db)
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
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        now=now,
    )
    db.commit()
    db.refresh(viewer)
    _set_live_cookie(response, viewer)
    return {
        "viewer_session_id": viewer.id,
        "media_url": MEDIA_URL,
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
    viewer = _viewer_from_cookie(db, blue_live_session)
    _authorize_existing_viewer(db, viewer, now=now)
    try:
        viewer = live_stream_service.heartbeat_viewer(db, viewer.id, now)
    except LookupError as exc:
        raise HTTPException(401, "观看授权已失效") from exc
    db.commit()
    db.refresh(viewer)
    _set_live_cookie(response, viewer)
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
    viewer = _viewer_from_cookie(db, blue_live_session)
    try:
        live_stream_service.end_viewer_session(db, viewer.id, datetime.utcnow())
    except LookupError as exc:
        raise HTTPException(401, "观看授权已失效") from exc
    db.commit()
    response.delete_cookie(LIVE_COOKIE_NAME, path="/")
    return response


@router.get("/api/live/authorize-media", status_code=204)
def authorize_live_media(
    blue_live_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    viewer = _viewer_from_cookie(db, blue_live_session)
    _authorize_existing_viewer(db, viewer, now=datetime.utcnow())
    return Response(status_code=204)


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
