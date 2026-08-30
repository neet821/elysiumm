from __future__ import annotations

import hashlib
import mimetypes
import os
import secrets
from datetime import timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import models
import transfer_service
from database import get_db
from dependencies import get_current_user


router = APIRouter(tags=["transfers"])


def admin_user(user: models.User = Depends(get_current_user)):
    if user.role != "admin" or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


def session_for_token(db: Session, token: str) -> models.TransferSession:
    transfer_service.cleanup_expired(db)
    session = db.query(models.TransferSession).filter(models.TransferSession.token_hash == transfer_service.token_hash(token)).first()
    if not session or session.expires_at <= transfer_service.utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "中转链接已失效")
    return session


def serialize_session(session: models.TransferSession, token: str | None = None) -> dict:
    payload = {
        "id": session.id,
        "created_at": serialize_datetime(session.created_at),
        "last_activity_at": serialize_datetime(session.last_activity_at),
        "expires_at": serialize_datetime(session.expires_at),
        "total_bytes": session.total_bytes,
        "max_bytes": session.max_bytes,
        "files": [
            {"id": item.id, "name": item.original_name, "size": item.file_size, "sha256": item.sha256, "created_at": serialize_datetime(item.created_at), "download_url": f"/api/transfers/{token}/files/{item.id}" if token else None}
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
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


@router.post("/api/admin/transfers", status_code=status.HTTP_201_CREATED)
def create_transfer(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    transfer_service.cleanup_expired(db)
    if db.query(models.TransferSession).count() >= transfer_service.TRANSFER_MAX_ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "有效中转链接已达到上限")
    if not transfer_service.has_disk_reserve():
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "服务器可用空间不足")
    token = transfer_service.new_token()
    now = transfer_service.utcnow()
    session = models.TransferSession(
        token_hash=transfer_service.token_hash(token),
        public_token=token,
        created_by=_admin.id,
        max_bytes=transfer_service.TRANSFER_MAX_SESSION_BYTES,
        last_activity_at=now,
        expires_at=now + timedelta(seconds=transfer_service.TRANSFER_TTL_SECONDS),
        created_at=now,
    )
    db.add(session); db.commit(); db.refresh(session)
    return serialize_session(session, token)


@router.post("/api/admin/transfers/current-link")
def current_transfer_link(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    transfer_service.cleanup_expired(db)
    session = db.query(models.TransferSession).order_by(models.TransferSession.created_at.desc()).first()
    if not session:
        if db.query(models.TransferSession).count() >= transfer_service.TRANSFER_MAX_ACTIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, "有效中转链接已达到上限")
        if not transfer_service.has_disk_reserve():
            raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "服务器可用空间不足")
        now = transfer_service.utcnow()
        token = transfer_service.new_token()
        session = models.TransferSession(
            token_hash=transfer_service.token_hash(token),
            public_token=token,
            created_by=_admin.id,
            max_bytes=transfer_service.TRANSFER_MAX_SESSION_BYTES,
            last_activity_at=now,
            expires_at=now + timedelta(seconds=transfer_service.TRANSFER_TTL_SECONDS),
            created_at=now,
        )
        db.add(session)
        db.flush()
    token = session.public_token
    if not token:
        token = transfer_service.new_token()
        session.token_hash = transfer_service.token_hash(token)
        session.public_token = token
    db.commit()
    db.refresh(session)
    return serialize_session(session, token)


@router.get("/api/admin/transfers")
def list_transfers(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    transfer_service.cleanup_expired(db)
    return [serialize_session(item) for item in db.query(models.TransferSession).order_by(models.TransferSession.created_at.desc()).all()]


@router.get("/api/admin/transfers/files")
def list_transfer_files(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    transfer_service.cleanup_expired(db)
    records = (
        db.query(models.TransferFile, models.TransferSession)
        .join(models.TransferSession, models.TransferFile.session_id == models.TransferSession.id)
        .order_by(models.TransferFile.created_at.desc(), models.TransferFile.id.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "name": item.original_name,
            "size": item.file_size,
            "sha256": item.sha256,
            "created_at": serialize_datetime(item.created_at),
            "transfer_id": session.id,
            "expires_at": serialize_datetime(session.expires_at),
            "download_url": f"/api/admin/transfers/files/{item.id}/download",
        }
        for item, session in records
    ]


@router.get("/api/admin/transfers/files/{file_id}/download")
def download_admin_transfer(file_id: int, request: Request, _admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    transfer_service.cleanup_expired(db)
    item, session = (
        db.query(models.TransferFile, models.TransferSession)
        .join(models.TransferSession, models.TransferFile.session_id == models.TransferSession.id)
        .filter(models.TransferFile.id == file_id)
        .first()
        or (None, None)
    )
    if not item or session.expires_at <= transfer_service.utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在或已清理")
    path = Path(item.storage_path).resolve()
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件已清理")

    size = path.stat().st_size
    start = 0
    end = size - 1
    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        start_text, _, end_text = range_header[6:].partition("-")
        start = int(start_text or 0)
        end = min(int(end_text) if end_text else size - 1, size - 1)
        if start > end or start >= size:
            raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "无效的 Range")
    transfer_service.refresh_expiry(session)
    db.commit()
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.original_name)}",
        "Content-Type": mimetypes.guess_type(item.original_name)[0] or "application/octet-stream",
    }
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(iter_file(path, start, end), status_code=206 if range_header else 200, headers=headers)


@router.delete("/api/admin/transfers/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer(session_id: int, _admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    session = db.query(models.TransferSession).filter(models.TransferSession.id == session_id).first()
    if not session: raise HTTPException(status.HTTP_404_NOT_FOUND, "中转链接不存在")
    transfer_service.delete_session_files(session); db.delete(session); db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/transfers/{token}")
def inspect_transfer(token: str, db: Session = Depends(get_db)):
    return serialize_session(session_for_token(db, token), token)


@router.put("/api/transfers/{token}")
async def upload_transfer(token: str, request: Request, filename: str | None = Query(None), x_filename: str | None = Header(None), db: Session = Depends(get_db)):
    session = session_for_token(db, token)
    name = transfer_service.safe_filename(x_filename or filename or request.headers.get("content-disposition", "").split("filename=")[-1])
    length = request.headers.get("content-length")
    expected = int(length) if length and length.isdigit() else None
    if expected is not None and expected > transfer_service.TRANSFER_MAX_FILE_BYTES: raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "单文件不能超过 2GB")
    if session.total_bytes + (expected or 0) > session.max_bytes: raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "中转链接总量不能超过 2GB")
    if expected is not None and not transfer_service.has_disk_reserve(expected): raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "服务器可用空间不足")
    root = transfer_service.ensure_storage(); stored = f"{secrets.token_hex(16)}.part"; temp_path = (root / stored).resolve(); final_path = None
    digest = hashlib.sha256(); size = 0
    try:
        with temp_path.open("xb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > transfer_service.TRANSFER_MAX_FILE_BYTES or session.total_bytes + size > session.max_bytes or not transfer_service.has_disk_reserve():
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "中转空间配额不足")
                digest.update(chunk); handle.write(chunk)
            handle.flush(); os.fsync(handle.fileno())
        if size == 0: raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能上传空文件")
        final_name = f"{secrets.token_hex(16)}.bin"; final_path = (root / final_name).resolve(); os.replace(temp_path, final_path)
        item = models.TransferFile(session=session, original_name=name, stored_name=final_name, storage_path=str(final_path), file_size=size, sha256=digest.hexdigest())
        session.total_bytes += size; transfer_service.refresh_expiry(session); db.add(item)
        rotated_token = transfer_service.new_token(); session.token_hash = transfer_service.token_hash(rotated_token); session.public_token = rotated_token
        db.commit(); db.refresh(item)
        return {"id": item.id, "name": item.original_name, "size": item.file_size, "sha256": item.sha256, "token": rotated_token, "url": f"/api/transfers/{rotated_token}", "download_url": f"/api/transfers/{rotated_token}/files/{item.id}"}
    except HTTPException:
        temp_path.unlink(missing_ok=True)
        if final_path: final_path.unlink(missing_ok=True)
        raise
    except Exception:
        temp_path.unlink(missing_ok=True)
        if final_path: final_path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "文件上传失败")


def iter_file(path: Path, start: int, end: int, chunk_size: int = 1024 * 1024):
    with path.open("rb") as handle:
        handle.seek(start); remaining = end - start + 1
        while remaining:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk: break
            remaining -= len(chunk); yield chunk


@router.get("/api/transfers/{token}/files/{file_id}")
def download_transfer(token: str, file_id: int, request: Request, db: Session = Depends(get_db)):
    session = session_for_token(db, token); item = db.query(models.TransferFile).filter(models.TransferFile.id == file_id, models.TransferFile.session_id == session.id).first()
    if not item: raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在")
    path = Path(item.storage_path).resolve()
    if not path.is_file(): raise HTTPException(status.HTTP_404_NOT_FOUND, "文件已清理")
    size = path.stat().st_size; start = 0; end = size - 1; range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        start_text, _, end_text = range_header[6:].partition("-")
        start = int(start_text or 0); end = min(int(end_text) if end_text else size - 1, size - 1)
        if start > end or start >= size: raise HTTPException(status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "无效的 Range")
    transfer_service.refresh_expiry(session); db.commit()
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1), "Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.original_name)}", "Content-Type": mimetypes.guess_type(item.original_name)[0] or "application/octet-stream"}
    if range_header: headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(iter_file(path, start, end), status_code=206 if range_header else 200, headers=headers)
