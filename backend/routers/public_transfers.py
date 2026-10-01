from __future__ import annotations

import hashlib
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import transfer_service
from database import get_db
from dependencies import get_current_admin as admin_user
from transfer_download_service import (
    create_transfer_download_response as create_transfer_download_response,
)
from transfer_session_service import (
    serialize_session as serialize_session,
    session_for_token as session_for_token,
)


router = APIRouter(tags=["transfers"])


@router.get("/api/transfers/{token}")
def inspect_transfer(token: str, db: Session = Depends(get_db)):
    return serialize_session(session_for_token(db, token), token)


@router.put("/api/transfers/{token}")
async def upload_transfer(
    token: str,
    request: Request,
    filename: str | None = Query(None),
    x_filename: str | None = Header(None),
    _admin: models.User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    session = session_for_token(db, token, for_update=True)
    content_disposition = request.headers.get("content-disposition", "")
    header_filename = content_disposition.split("filename=")[-1]
    name = transfer_service.safe_filename(x_filename or filename or header_filename)

    length = request.headers.get("content-length")
    expected = int(length) if length and length.isdigit() else None
    if expected is not None and expected > transfer_service.TRANSFER_MAX_FILE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "单文件不能超过 2GB",
        )
    reserved_bytes = (
        db.query(func.coalesce(func.sum(models.TusUploadReservation.upload_length), 0))
        .filter(
            models.TusUploadReservation.transfer_session_id == session.id,
            models.TusUploadReservation.status.in_(("creating", "active")),
            models.TusUploadReservation.expires_at > transfer_service.utcnow(),
        )
        .scalar()
    ) or 0
    if session.total_bytes + reserved_bytes + (expected or 0) > session.max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "中转链接总量不能超过 2GB",
        )
    if expected is not None and not transfer_service.has_disk_reserve(expected):
        raise HTTPException(
            status.HTTP_507_INSUFFICIENT_STORAGE,
            "服务器可用空间不足",
        )

    root = transfer_service.ensure_storage()
    stored_name = f"{secrets.token_hex(16)}.part"
    temp_path = (root / stored_name).resolve()
    final_path = None
    digest = hashlib.sha256()
    size = 0

    try:
        with temp_path.open("xb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                exceeds_file_limit = size > transfer_service.TRANSFER_MAX_FILE_BYTES
                exceeds_session_limit = (
                    session.total_bytes + reserved_bytes + size > session.max_bytes
                )
                if (
                    exceeds_file_limit
                    or exceeds_session_limit
                    or not transfer_service.has_disk_reserve()
                ):
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "中转空间配额不足",
                    )
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())

        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能上传空文件")

        final_name = f"{secrets.token_hex(16)}.bin"
        final_path = (root / final_name).resolve()
        os.replace(temp_path, final_path)
        item = models.TransferFile(
            session=session,
            original_name=name,
            stored_name=final_name,
            storage_path=str(final_path),
            file_size=size,
            sha256=digest.hexdigest(),
        )
        session.total_bytes += size
        transfer_service.refresh_expiry(session)
        db.add(item)

        rotated_token = transfer_service.new_token()
        session.token_hash = transfer_service.token_hash(rotated_token)
        session.public_token = rotated_token
        db.commit()
        db.refresh(item)
        return {
            "id": item.id,
            "name": item.original_name,
            "size": item.file_size,
            "sha256": item.sha256,
            "token": rotated_token,
            "url": f"/api/transfers/{rotated_token}",
            "download_url": f"/api/transfers/{rotated_token}/files/{item.id}",
        }
    except HTTPException:
        temp_path.unlink(missing_ok=True)
        if final_path:
            final_path.unlink(missing_ok=True)
        raise
    except Exception:
        temp_path.unlink(missing_ok=True)
        if final_path:
            final_path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "文件上传失败",
        )


@router.get("/api/transfers/{token}/files/{file_id}")
def download_transfer(
    token: str,
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    session = session_for_token(db, token)
    item = (
        db.query(models.TransferFile)
        .filter(
            models.TransferFile.id == file_id,
            models.TransferFile.session_id == session.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在")
    return create_transfer_download_response(db, session, item, request)
