from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session

import models
from live_geo import VisitorFingerprint, identify_visitor


MAX_HEARTBEAT_GAP_SECONDS = 60


@dataclass(frozen=True)
class LiveAccessDecision:
    allowed: bool
    reason: str
    user_id: int | None = None
    invite_id: int | None = None


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_secret() -> tuple[str, str, str]:
    raw_token = secrets.token_urlsafe(32)
    return raw_token, token_digest(raw_token), raw_token[-6:]


def get_or_create_setting(db: Session) -> models.LiveSetting:
    setting = (
        db.query(models.LiveSetting)
        .order_by(models.LiveSetting.id.asc())
        .first()
    )
    if setting is None:
        setting = models.LiveSetting()
        db.add(setting)
        db.flush()
    return setting


def find_active_invite(
    db: Session,
    raw_token: str | None,
    *,
    now: datetime,
) -> models.LiveInvite | None:
    if not raw_token or len(raw_token) > 512:
        return None
    digest = token_digest(raw_token)
    invite = (
        db.query(models.LiveInvite)
        .filter(models.LiveInvite.token_hash == digest)
        .first()
    )
    if invite is None or not hmac.compare_digest(invite.token_hash, digest):
        return None
    if invite.revoked_at is not None:
        return None
    if invite.expires_at is not None and invite.expires_at <= now:
        return None
    return invite


def authorize_viewer(
    db: Session,
    *,
    user: models.User | None,
    invite_token: str | None,
    now: datetime,
) -> LiveAccessDecision:
    setting = get_or_create_setting(db)
    if user is not None and user.role == "admin" and user.is_active:
        return LiveAccessDecision(
            True,
            "administrator",
            user_id=user.id,
        )
    if not setting.viewing_enabled:
        return LiveAccessDecision(False, "viewing_disabled")
    if setting.access_mode == "public":
        return LiveAccessDecision(
            True,
            "public",
            user_id=user.id if user is not None and user.is_active else None,
        )
    if setting.access_mode == "allowlist":
        if user is None or not user.is_active:
            return LiveAccessDecision(False, "login_required")
        allowed = (
            db.query(models.LiveAllowedUser)
            .filter(models.LiveAllowedUser.user_id == user.id)
            .first()
        )
        return LiveAccessDecision(
            allowed is not None,
            "allowlist" if allowed is not None else "forbidden",
            user_id=user.id,
        )
    if setting.access_mode == "invite":
        invite = find_active_invite(db, invite_token, now=now)
        if invite is None:
            return LiveAccessDecision(False, "invite_invalid")
        invite.last_used_at = now
        db.flush()
        return LiveAccessDecision(
            True,
            "invite",
            invite_id=invite.id,
        )
    return LiveAccessDecision(False, "forbidden")


def open_viewer_session(
    db: Session,
    *,
    live_session: models.LiveSession,
    decision: LiveAccessDecision,
    client_ip: str,
    user_agent: str,
    now: datetime,
    fingerprint: VisitorFingerprint | None = None,
) -> models.LiveViewerSession:
    if not decision.allowed:
        raise PermissionError(decision.reason)
    resolved = fingerprint or identify_visitor(client_ip, user_agent)
    viewer = (
        db.query(models.LiveViewerSession)
        .filter(
            models.LiveViewerSession.live_session_id == live_session.id,
            models.LiveViewerSession.ip_address == client_ip[:45],
        )
        .order_by(models.LiveViewerSession.first_seen_at.asc())
        .first()
    )
    if viewer is not None:
        if decision.user_id is not None:
            viewer.user_id = decision.user_id
        if decision.invite_id is not None:
            viewer.invite_id = decision.invite_id
        viewer.last_seen_at = now
        viewer.ended_at = None
        db.flush()
        return viewer
    viewer = models.LiveViewerSession(
        live_session_id=live_session.id,
        user_id=decision.user_id,
        invite_id=decision.invite_id,
        ip_address=client_ip[:45],
        country=resolved.country,
        region=resolved.region,
        city=resolved.city,
        device_type=resolved.device_type,
        operating_system=resolved.operating_system,
        browser=resolved.browser,
        first_seen_at=now,
        last_seen_at=now,
        watched_seconds=0,
    )
    db.add(viewer)
    db.flush()
    return viewer


def heartbeat_viewer(
    db: Session,
    viewer_session_id: str,
    now: datetime,
) -> models.LiveViewerSession:
    viewer = db.get(models.LiveViewerSession, viewer_session_id)
    if viewer is None or viewer.ended_at is not None:
        raise LookupError("观看会话不存在或已结束")
    elapsed = max(0, int((now - viewer.last_seen_at).total_seconds()))
    viewer.watched_seconds += min(elapsed, MAX_HEARTBEAT_GAP_SECONDS)
    viewer.last_seen_at = now
    db.flush()
    return viewer


def end_viewer_session(
    db: Session,
    viewer_session_id: str,
    now: datetime,
) -> models.LiveViewerSession:
    viewer = heartbeat_viewer(db, viewer_session_id, now)
    viewer.ended_at = now
    db.flush()
    return viewer


def purge_viewer_history(
    db: Session,
    *,
    before: datetime,
    live_session_id: int | None = None,
) -> int:
    query = db.query(models.LiveViewerSession).filter(
        models.LiveViewerSession.last_seen_at < before
    )
    if live_session_id is not None:
        query = query.filter(
            models.LiveViewerSession.live_session_id == live_session_id
        )
    removed = query.delete(synchronize_session=False)
    db.flush()
    return int(removed)
