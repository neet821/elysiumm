import hashlib
import secrets
from datetime import datetime, timedelta

import models

DEFAULT_DEVICE_TOKEN_DAYS = 90
MAX_DEVICE_TOKEN_DAYS = 365
MAX_DEVICE_TOKEN_LENGTH = 512
INVALID_DEVICE_CREDENTIAL = "无效的同步设备凭据"


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validate_expiry_days(expires_in_days: int) -> int:
    if not 1 <= expires_in_days <= MAX_DEVICE_TOKEN_DAYS:
        raise ValueError("设备凭据有效期必须为 1 到 365 天")
    return expires_in_days


def _new_device_token() -> str:
    return secrets.token_urlsafe(32)


def create_device(
    db,
    *,
    name: str,
    expires_in_days: int = DEFAULT_DEVICE_TOKEN_DAYS,
    now: datetime | None = None,
):
    normalized_name = " ".join(name.split())
    if not normalized_name or len(normalized_name) > 100 or any(ord(char) < 32 for char in name):
        raise ValueError("设备名称必须为 1 到 100 个可见字符")
    days = _validate_expiry_days(expires_in_days)
    current_time = now or datetime.utcnow()
    token = _new_device_token()
    item = models.SyncDevice(
        name=normalized_name,
        device_token_hash=hash_device_token(token),
        token_hint=token[-4:],
        token_expires_at=current_time + timedelta(days=days),
        status="offline",
    )
    db.add(item)
    db.flush()
    return item, token


def rotate_device_credential(
    db,
    item,
    *,
    expires_in_days: int = DEFAULT_DEVICE_TOKEN_DAYS,
    now: datetime | None = None,
) -> str:
    days = _validate_expiry_days(expires_in_days)
    current_time = now or datetime.utcnow()
    token = _new_device_token()
    item.device_token_hash = hash_device_token(token)
    item.token_hint = token[-4:]
    item.token_expires_at = current_time + timedelta(days=days)
    item.rotated_at = current_time
    item.revoked_at = None
    item.status = "offline"
    item.scan_requested = False
    db.flush()
    return token


def revoke_device(db, item, *, now: datetime | None = None):
    item.revoked_at = now or datetime.utcnow()
    item.status = "revoked"
    item.is_paused = True
    item.scan_requested = False
    db.flush()
    return item


def authenticate_device(db, token: str, *, now: datetime | None = None):
    if not isinstance(token, str) or not token or len(token) > MAX_DEVICE_TOKEN_LENGTH:
        raise ValueError(INVALID_DEVICE_CREDENTIAL)
    token_hash = hash_device_token(token)
    item = db.query(models.SyncDevice).filter(models.SyncDevice.device_token_hash == token_hash).first()
    current_time = now or datetime.utcnow()
    if (
        not item
        or item.revoked_at is not None
        or (item.token_expires_at is not None and item.token_expires_at <= current_time)
    ):
        raise ValueError(INVALID_DEVICE_CREDENTIAL)
    item.status = "online"
    item.last_seen_at = current_time
    db.commit()
    return item
