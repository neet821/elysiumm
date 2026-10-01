from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
import schemas
from admin_audit import add_admin_audit
from config import config
from database import get_db
from live_stream_service import generate_secret
from routers.live_admin_common import _rate_limit, active_administrator


router = APIRouter()


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
            kind="publish", token_hash=digest, token_hint=hint
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
    rows = (
        _active_invite_query(db)
        .order_by(models.LiveInvite.created_at.desc())
        .limit(1)
        .all()
    )
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
            "invite_url": f"{config.LIVE_PUBLIC_BASE_URL}/live?invite={quote(raw)}",
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
