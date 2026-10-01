"""兼容同步入口：组合管理员设备管理与同步客户端协议路由。"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import models
import public_sync_service
import schemas
from database import get_db
from routers import public_sync_admin
from routers.public_sync_admin import (
    _device_or_404 as _device_or_404,
    _update_device_flag as _update_device_flag,
    _validate_device_name as _validate_device_name,
    admin as admin,
    create_device as create_device,
    dashboard as dashboard,
    pause as pause,
    request_scan as request_scan,
    resume as resume,
    revoke_device as revoke_device,
    rotate_device as rotate_device,
)

router = APIRouter()
device_router = APIRouter(prefix="/api/sync", tags=["public-sync"])


def device(db: Session = Depends(get_db), x_sync_token: str = Header(default="")):
    try:
        return public_sync_service.authenticate_device(db, x_sync_token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


@device_router.post("/heartbeat")
def heartbeat(db: Session = Depends(get_db), item=Depends(device)):
    requested = item.scan_requested
    item.scan_requested = False
    db.commit()
    return {"device_id": item.id, "is_paused": item.is_paused, "scan_requested": requested}


@device_router.post("/files", response_model=schemas.SyncFileSummary)
def upload(
    relative_path: str = Form(...),
    expected_size: int | None = Form(None, ge=0),
    expected_sha256: str | None = Form(None, max_length=64),
    mtime: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    item=Depends(device),
):
    try:
        parsed = datetime.fromisoformat(mtime) if mtime else None
        record = public_sync_service.save_upload(
            db,
            item,
            relative_path,
            file.file,
            parsed,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )
        return public_sync_service.serialize_file(record)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@device_router.post("/files/chunks", response_model=schemas.SyncFileSummary)
def upload_chunk(
    relative_path: str = Form(...),
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    expected_size: int = Form(...),
    expected_sha256: str | None = Form(None, max_length=64),
    mtime: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    item=Depends(device),
):
    try:
        parsed = datetime.fromisoformat(mtime) if mtime else None
        record = public_sync_service.save_chunk(
            db,
            item,
            relative_path,
            upload_id,
            chunk_index,
            total_chunks,
            expected_size,
            file.file,
            parsed,
            expected_sha256=expected_sha256,
        )
        return public_sync_service.serialize_file(record)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@device_router.post("/errors")
def report_error(
    message: str = Form(..., min_length=1, max_length=1000),
    relative_path: str | None = Form(None, max_length=1000),
    db: Session = Depends(get_db),
    item=Depends(device),
):
    try:
        normalized_path = public_sync_service.safe_relative_path(relative_path) if relative_path else None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.add(models.SyncEvent(
        device_id=item.id,
        relative_path=normalized_path,
        event_type="error",
        status="failed",
        message=message,
    ))
    db.commit()
    return {"recorded": True}


@device_router.delete("/files")
def remove(relative_path: str, db: Session = Depends(get_db), item=Depends(device)):
    try:
        public_sync_service.delete_file(db, item, relative_path)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"deleted": True, "relative_path": public_sync_service.safe_relative_path(relative_path)}


router.include_router(public_sync_admin.router)
router.include_router(device_router)
