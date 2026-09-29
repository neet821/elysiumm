"""Upload policy, quota reservations and atomic publication for tus uploads."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import admin_file_service
import models
import transfer_service
from config import config
from file_integrity import sha256_file
from tus_runtime import (
    _publish_staged_file as _publish_staged_file,
    create_tusd_client as create_tusd_client,
    has_disk_reserve as has_disk_reserve,
    re_full_upload_id as re_full_upload_id,
    tus_staging_file as tus_staging_file,
    tusd_url as tusd_url,
)
from tus_admin_file_service import finalize_admin_file_upload
from tus_transfer_file_service import finalize_transfer_file_upload


ACTIVE_STATUSES = ("creating", "active")


def utcnow() -> datetime:
    return datetime.utcnow()


def reserve_upload(
    db: Session,
    *,
    owner: models.User,
    filename: str,
    content_type: str | None,
    purpose: str,
    upload_length: int,
    session_id: str | None,
) -> models.TusUploadReservation:
    if upload_length <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能上传空文件")

    transfer_session = None
    stored_name = filename
    normalized_content_type = content_type
    if purpose == "admin_file":
        try:
            stored_name, extension = admin_file_service.validate_original_name(filename)
            normalized_content_type = admin_file_service.validate_declared_content_type(
                extension, content_type
            )
        except admin_file_service.AdminFileValidationError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        if upload_length > config.MAX_ADMIN_FILE_SIZE:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "文件超过大小限制",
            )
        if not has_disk_reserve(config.ADMIN_FILES_STORAGE_DIR, upload_length):
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE,
                "服务器可用空间不足",
            )
    elif purpose == "transfer_file":
        if not session_id or not session_id.isdecimal():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "中转会话无效")
        transfer_session = (
            db.query(models.TransferSession)
            .filter(models.TransferSession.id == int(session_id))
            .with_for_update()
            .first()
        )
        if (
            transfer_session is None
            or transfer_session.created_by != owner.id
            or transfer_session.expires_at <= utcnow()
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "中转会话不存在")
        stored_name = transfer_service.safe_filename(filename)
        if upload_length > transfer_service.TRANSFER_MAX_FILE_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "单文件不能超过 2GB",
            )

        reserved_bytes = (
            db.query(func.coalesce(func.sum(models.TusUploadReservation.upload_length), 0))
            .filter(
                models.TusUploadReservation.transfer_session_id == transfer_session.id,
                models.TusUploadReservation.status.in_(ACTIVE_STATUSES),
            )
            .scalar()
        ) or 0
        active_count = (
            db.query(models.TusUploadReservation.id)
            .filter(
                models.TusUploadReservation.transfer_session_id == transfer_session.id,
                models.TusUploadReservation.status.in_(ACTIVE_STATUSES),
            )
            .count()
        )
        if active_count >= transfer_service.TRANSFER_MAX_ACTIVE:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "同时上传数量已达上限")
        if transfer_session.total_bytes + reserved_bytes + upload_length > transfer_session.max_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "中转链接总量不能超过 2GB",
            )
        if not has_disk_reserve(transfer_service.TRANSFER_ROOT, upload_length):
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE,
                "服务器可用空间不足",
            )
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上传用途无效")

    now = utcnow()
    reservation = models.TusUploadReservation(
        owner_user_id=owner.id,
        purpose=purpose,
        transfer_session_id=transfer_session.id if transfer_session else None,
        original_name=stored_name,
        content_type=normalized_content_type,
        upload_length=upload_length,
        upload_offset=0,
        status="creating",
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(seconds=config.TUS_UPLOAD_TTL_SECONDS),
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def reservation_for_owner(
    db: Session,
    upload_id: str,
    owner: models.User,
    *,
    allowed_statuses: tuple[str, ...] = ("creating", "active", "complete"),
) -> models.TusUploadReservation:
    reservation = (
        db.query(models.TusUploadReservation)
        .filter(models.TusUploadReservation.upload_id == upload_id)
        .with_for_update()
        .first()
    )
    if reservation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "上传不存在")
    if reservation.owner_user_id != owner.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问此上传")
    if reservation.expires_at <= utcnow() and reservation.status in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_410_GONE, "上传已过期")
    if reservation.status not in allowed_statuses:
        raise HTTPException(status.HTTP_410_GONE, "上传已失效")
    return reservation


def refresh_transfer_session(
    db: Session,
    reservation: models.TusUploadReservation,
) -> None:
    if reservation.purpose != "transfer_file" or not reservation.transfer_session_id:
        return
    session = (
        db.query(models.TransferSession)
        .filter(models.TransferSession.id == reservation.transfer_session_id)
        .with_for_update()
        .first()
    )
    if session is not None:
        transfer_service.refresh_expiry(session)


def finalize_upload(
    db: Session,
    *,
    reservation: models.TusUploadReservation,
) -> dict:
    reservation = (
        db.query(models.TusUploadReservation)
        .filter(models.TusUploadReservation.id == reservation.id)
        .with_for_update()
        .one()
    )
    if reservation.status == "complete" and reservation.result_payload:
        return json.loads(reservation.result_payload)
    if reservation.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "上传尚未就绪")

    source = tus_staging_file(reservation.upload_id)
    if not source.is_file() or source.is_symlink():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "上传暂存文件不可用")
    if source.stat().st_size != reservation.upload_length:
        raise HTTPException(status.HTTP_409_CONFLICT, "上传文件长度不完整")
    digest = sha256_file(source)
    final_path: Path | None = None

    try:
        if reservation.purpose == "admin_file":
            payload, final_path = finalize_admin_file_upload(
                db,
                reservation=reservation,
                source=source,
                digest=digest,
            )
        else:
            payload, final_path = finalize_transfer_file_upload(
                db,
                reservation=reservation,
                source=source,
                digest=digest,
            )
        reservation.status = "complete"
        reservation.upload_offset = reservation.upload_length
        reservation.last_activity_at = utcnow()
        reservation.completed_at = reservation.last_activity_at
        reservation.result_payload = json.dumps(payload, ensure_ascii=False)
        db.commit()
        source.unlink(missing_ok=True)
        source.with_suffix(".info").unlink(missing_ok=True)
        return payload
    except admin_file_service.AdminFileValidationError as exc:
        db.rollback()
        if final_path:
            final_path.unlink(missing_ok=True)
        reservation = db.query(models.TusUploadReservation).filter_by(id=reservation.id).one()
        reservation.status = "failed"
        reservation.failure_code = exc.code
        reservation.last_activity_at = utcnow()
        db.commit()
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception:
        db.rollback()
        if final_path:
            final_path.unlink(missing_ok=True)
        raise


async def cleanup_expired_uploads(db: Session, *, now: datetime | None = None) -> int:
    """Expire abandoned reservations, deleting tusd state before releasing quota."""

    current = now or utcnow()
    expired = (
        db.query(models.TusUploadReservation)
        .filter(
            models.TusUploadReservation.status.in_(ACTIVE_STATUSES),
            models.TusUploadReservation.expires_at <= current,
        )
        .all()
    )
    cleaned = 0
    for item in expired:
        if item.upload_id:
            client = create_tusd_client()
            try:
                response = await client.delete(
                    tusd_url(item.upload_id),
                    headers={"Tus-Resumable": "1.0.0"},
                )
            except httpx.HTTPError:
                continue
            finally:
                await client.aclose()
            if response.status_code not in {status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND}:
                continue
            data_path = tus_staging_file(item.upload_id)
            data_path.unlink(missing_ok=True)
            data_path.with_suffix(".info").unlink(missing_ok=True)
            item.status = "cancelled"
        else:
            item.status = "failed"
            item.failure_code = "tusd_creation_expired"
        item.last_activity_at = current
        cleaned += 1

    if cleaned:
        db.commit()

    # A tusd POST can succeed while its response is lost. Such an upload has
    # no database ID; remove only stale, UUID-shaped files in our dedicated dir.
    root = Path(config.TUS_UPLOAD_DIR).expanduser().resolve()
    if root.is_dir():
        active_ids = {
            row[0]
            for row in db.query(models.TusUploadReservation.upload_id)
            .filter(
                models.TusUploadReservation.status.in_(ACTIVE_STATUSES),
                models.TusUploadReservation.expires_at > current,
                models.TusUploadReservation.upload_id.isnot(None),
            )
            .all()
        }
        oldest = current.timestamp() - config.TUS_UPLOAD_TTL_SECONDS
        for path in root.iterdir():
            upload_id = path.stem if path.suffix == ".info" else path.name
            if not re_full_upload_id(upload_id) or upload_id in active_ids:
                continue
            try:
                if path.is_file() and not path.is_symlink() and path.stat().st_mtime <= oldest:
                    path.unlink(missing_ok=True)
            except OSError:
                continue

    return cleaned
