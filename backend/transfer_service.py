from __future__ import annotations

import hashlib
import os
import secrets
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import models


TRANSFER_TTL_SECONDS = int(os.getenv("TRANSFER_TTL_SECONDS", "300"))
TRANSFER_MAX_FILE_BYTES = int(os.getenv("TRANSFER_MAX_FILE_BYTES", str(2 * 1024**3)))
TRANSFER_MAX_SESSION_BYTES = int(os.getenv("TRANSFER_MAX_SESSION_BYTES", str(2 * 1024**3)))
TRANSFER_MAX_ACTIVE = int(os.getenv("TRANSFER_MAX_ACTIVE", "3"))
TRANSFER_DISK_RESERVE_BYTES = int(os.getenv("TRANSFER_DISK_RESERVE_BYTES", str(5 * 1024**3)))
TRANSFER_ROOT = Path(os.getenv("TRANSFER_STORAGE_DIR", "/var/lib/elysiumm/transfers")).expanduser().resolve()


def utcnow() -> datetime:
    return datetime.utcnow()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_storage() -> Path:
    TRANSFER_ROOT.mkdir(parents=True, exist_ok=True)
    return TRANSFER_ROOT


def has_disk_reserve(required_bytes: int = 0) -> bool:
    usage = shutil.disk_usage(ensure_storage())
    return usage.free >= TRANSFER_DISK_RESERVE_BYTES + max(0, required_bytes)


def safe_filename(value: str | None) -> str:
    name = Path((value or "unnamed-file").replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        return "unnamed-file"
    return name[:255]


def refresh_expiry(session: models.TransferSession, now: datetime | None = None) -> None:
    current = now or utcnow()
    session.last_activity_at = current
    session.expires_at = current + timedelta(seconds=TRANSFER_TTL_SECONDS)


def delete_session_files(session: models.TransferSession) -> int:
    removed = 0
    for item in session.files:
        path = Path(item.storage_path).resolve()
        try:
            path.relative_to(ensure_storage())
        except ValueError:
            continue
        if path.is_file():
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def cleanup_expired(db, now: datetime | None = None) -> int:
    current = now or utcnow()
    sessions = db.query(models.TransferSession).filter(models.TransferSession.expires_at <= current).all()
    count = 0
    for session in sessions:
        delete_session_files(session)
        db.delete(session)
        count += 1
    if count:
        db.commit()
    return count
