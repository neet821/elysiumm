from datetime import timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import models
import transfer_service


def session_for_token(
    db: Session,
    token: str,
    *,
    for_update: bool = False,
) -> models.TransferSession:
    transfer_service.cleanup_expired(db)
    token_hash = transfer_service.token_hash(token)
    query = db.query(models.TransferSession).filter(
        models.TransferSession.token_hash == token_hash
    )
    if for_update:
        query = query.with_for_update()
    session = query.first()
    if not session or session.expires_at <= transfer_service.utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "中转链接已失效")
    return session


def serialize_session(
    session: models.TransferSession,
    token: str | None = None,
) -> dict:
    payload = {
        "id": session.id,
        "created_at": serialize_datetime(session.created_at),
        "last_activity_at": serialize_datetime(session.last_activity_at),
        "expires_at": serialize_datetime(session.expires_at),
        "total_bytes": session.total_bytes,
        "max_bytes": session.max_bytes,
        "files": [
            {
                "id": item.id,
                "name": item.original_name,
                "size": item.file_size,
                "sha256": item.sha256,
                "created_at": serialize_datetime(item.created_at),
                "download_url": (
                    f"/api/transfers/{token}/files/{item.id}" if token else None
                ),
            }
            for item in session.files
        ],
    }
    if token:
        payload["token"] = token
        payload["url"] = f"/api/transfers/{token}"
    return payload


def serialize_datetime(value):
    if value is None:
        return None
    aware = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return aware.isoformat().replace("+00:00", "Z")


def get_or_create_current_session(
    db: Session,
    admin_id: int,
) -> tuple[models.TransferSession, str]:
    transfer_service.cleanup_expired(db)
    sessions = (
        db.query(models.TransferSession)
        .order_by(models.TransferSession.created_at.desc())
        .all()
    )
    session = sessions[0] if sessions else None
    obsolete_files = [
        item for obsolete in sessions[1:] for item in obsolete.files
    ]
    combined_total = (session.total_bytes if session else 0) + sum(
        item.file_size for item in obsolete_files
    )
    if session and combined_total > session.max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "现有中转文件总量超过 2GB，无法合并",
        )
    for obsolete in sessions[1:]:
        for item in obsolete.files:
            item.session = session
        db.delete(obsolete)
    if session:
        session.total_bytes = combined_total
    if session is None:
        if not transfer_service.has_disk_reserve():
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE,
                "服务器可用空间不足",
            )
        now = transfer_service.utcnow()
        token = transfer_service.new_token()
        session = models.TransferSession(
            token_hash=transfer_service.token_hash(token),
            public_token=token,
            created_by=admin_id,
            max_bytes=transfer_service.TRANSFER_MAX_SESSION_BYTES,
            last_activity_at=now,
            expires_at=now + timedelta(seconds=transfer_service.TRANSFER_TTL_SECONDS),
            created_at=now,
        )
        db.add(session)
    else:
        token = session.public_token
        if not token:
            token = transfer_service.new_token()
            session.token_hash = transfer_service.token_hash(token)
            session.public_token = token
    return session, token
