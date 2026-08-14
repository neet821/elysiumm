from datetime import datetime

from sqlalchemy import func, text

import models
from config import config


MAX_OVERVIEW_FAILURES = 10
MAX_SECURITY_ROWS = 100
ACTIVE_MEDIA_ROOM_STATES = ("active", "idle")
ACTIVE_GAME_ROOM_STATES = ("waiting", "playing")


def _count(db, model, *criteria) -> int:
    query = db.query(func.count(model.id))
    if criteria:
        query = query.filter(*criteria)
    return int(query.scalar() or 0)


def _count_and_bytes(db, model, size_column, *criteria) -> tuple[int, int]:
    query = db.query(func.count(model.id), func.coalesce(func.sum(size_column), 0))
    if criteria:
        query = query.filter(*criteria)
    count, total_bytes = query.one()
    return int(count or 0), int(total_bytes or 0)


def _admin_audit_rows(db, *, limit: int, failures_only: bool = False) -> list[dict]:
    query = (
        db.query(models.AdminAuditLog, models.User.username)
        .outerjoin(models.User, models.User.id == models.AdminAuditLog.actor_id)
    )
    if failures_only:
        query = query.filter(models.AdminAuditLog.outcome.in_(("failed", "rate_limited")))
    rows = (
        query.order_by(models.AdminAuditLog.created_at.desc(), models.AdminAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "actor_username": username,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "outcome": row.outcome,
            "created_at": row.created_at,
        }
        for row, username in rows
    ]


def _realtime_audit_rows(db, *, limit: int) -> list[dict]:
    rows = (
        db.query(models.RealtimeEventAuditLog, models.User.username)
        .outerjoin(models.User, models.User.id == models.RealtimeEventAuditLog.actor_id)
        .order_by(
            models.RealtimeEventAuditLog.created_at.desc(),
            models.RealtimeEventAuditLog.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "actor_username": username,
            "event_name": row.event_name,
            "room_id": row.room_id,
            "outcome": row.outcome,
            "created_at": row.created_at,
        }
        for row, username in rows
    ]


def overview_payload(db, *, now: datetime | None = None) -> dict:
    generated_at = now or datetime.utcnow()
    db.execute(text("SELECT 1"))

    manual_count, manual_bytes = _count_and_bytes(
        db,
        models.AdminFile,
        models.AdminFile.file_size,
    )
    synced_count, synced_bytes = _count_and_bytes(
        db,
        models.SyncFile,
        models.SyncFile.file_size,
        models.SyncFile.sync_status != "deleted",
    )
    latest_backup = (
        db.query(models.BackupJob)
        .order_by(models.BackupJob.created_at.desc(), models.BackupJob.id.desc())
        .first()
    )

    return {
        "generated_at": generated_at,
        "health": {
            "status": "ok",
            "database": "connected",
            "storage": "database metadata available",
        },
        "users": {
            "total": _count(db, models.User),
            "active": _count(db, models.User, models.User.is_active.is_(True)),
            "inactive": _count(db, models.User, models.User.is_active.is_(False)),
            "administrators": _count(db, models.User, models.User.role == "admin"),
        },
        "rooms": {
            "media_active": _count(
                db,
                models.SyncRoom,
                models.SyncRoom.lifecycle_status.in_(ACTIVE_MEDIA_ROOM_STATES),
            ),
            "game_active": _count(
                db,
                models.GameRoom,
                models.GameRoom.deleted_at.is_(None),
                models.GameRoom.status.in_(ACTIVE_GAME_ROOM_STATES),
            ),
        },
        "files": {
            "manual_count": manual_count,
            "manual_bytes": manual_bytes,
            "synced_count": synced_count,
            "synced_bytes": synced_bytes,
            "active_uploads": _count(
                db,
                models.SyncUpload,
                models.SyncUpload.status == "uploading",
            ),
        },
        "sync": {
            "devices": _count(db, models.SyncDevice),
            "online": _count(db, models.SyncDevice, models.SyncDevice.status == "online"),
            "paused": _count(db, models.SyncDevice, models.SyncDevice.is_paused.is_(True)),
            "revoked": _count(
                db,
                models.SyncDevice,
                models.SyncDevice.revoked_at.is_not(None),
            ),
            "expired": _count(
                db,
                models.SyncDevice,
                models.SyncDevice.token_expires_at.is_not(None),
                models.SyncDevice.token_expires_at <= generated_at,
            ),
        },
        "books": {
            "total": _count(db, models.Book),
            "published": _count(db, models.Book, models.Book.is_public.is_(True)),
            "lists": _count(db, models.BookList),
        },
        "backups": {
            "jobs": _count(db, models.BackupJob),
            "latest_status": latest_backup.status if latest_backup else None,
            "latest_created_at": latest_backup.created_at if latest_backup else None,
        },
        "recent_failures": _admin_audit_rows(
            db,
            limit=MAX_OVERVIEW_FAILURES,
            failures_only=True,
        ),
    }


def security_payload(db, *, limit: int = 50, now: datetime | None = None) -> dict:
    if not 1 <= limit <= MAX_SECURITY_ROWS:
        raise ValueError("数量限制必须在 1 到 100 之间")
    generated_at = now or datetime.utcnow()
    configured_origins = [
        origin.strip()
        for origin in getattr(config, "CORS_ORIGINS", [])
        if origin and origin.strip()
    ]
    return {
        "generated_at": generated_at,
        "counts": {
            "inactive_users": _count(db, models.User, models.User.is_active.is_(False)),
            "revoked_devices": _count(
                db,
                models.SyncDevice,
                models.SyncDevice.revoked_at.is_not(None),
            ),
            "expired_devices": _count(
                db,
                models.SyncDevice,
                models.SyncDevice.token_expires_at.is_not(None),
                models.SyncDevice.token_expires_at <= generated_at,
            ),
            "admin_failed": _count(
                db,
                models.AdminAuditLog,
                models.AdminAuditLog.outcome == "failed",
            ),
            "admin_rate_limited": _count(
                db,
                models.AdminAuditLog,
                models.AdminAuditLog.outcome == "rate_limited",
            ),
            "realtime_failed": _count(
                db,
                models.RealtimeEventAuditLog,
                models.RealtimeEventAuditLog.outcome == "failed",
            ),
            "realtime_rate_limited": _count(
                db,
                models.RealtimeEventAuditLog,
                models.RealtimeEventAuditLog.outcome == "rate_limited",
            ),
        },
        "configuration": {
            "socket_auth_required": True,
            "cors_credentials_enabled": True,
            "cors_allowed_origin_count": len(set(configured_origins)),
            "cors_wildcard_configured": any("*" in item for item in configured_origins),
        },
        "capabilities": {
            "web_session_inventory_available": False,
            "web_session_inventory_reason": (
                "此应用不会在服务端持久保存网页会话。"
            ),
        },
        "admin_audit": _admin_audit_rows(db, limit=limit),
        "realtime_audit": _realtime_audit_rows(db, limit=limit),
    }
