from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import models
import public_sync_service
import schemas
from admin_audit import add_admin_audit
from database import get_db
from dependencies import get_current_user

router = APIRouter(prefix="/api/sync", tags=["public-sync"])


def admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


def device(db: Session = Depends(get_db), x_sync_token: str = Header(default="")):
    try:
        return public_sync_service.authenticate_device(db, x_sync_token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


def _device_or_404(db: Session, device_id: int):
    item = db.get(models.SyncDevice, device_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "设备不存在")
    return item


def _validate_device_name(name: str) -> str:
    normalized = " ".join(name.split())
    if not normalized or len(normalized) > 100 or any(ord(char) < 32 for char in name):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "设备名称必须为 1 到 100 个可见字符",
        )
    return normalized


@router.post(
    "/devices",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.SyncDeviceSecretResponse,
)
def create_device(
    name: str = Form(..., min_length=1, max_length=100),
    expires_in_days: int = Form(public_sync_service.DEFAULT_DEVICE_TOKEN_DAYS, ge=1, le=365),
    db: Session = Depends(get_db),
    user=Depends(admin),
):
    try:
        item, device_token = public_sync_service.create_device(
            db,
            name=_validate_device_name(name),
            expires_in_days=expires_in_days,
        )
        add_admin_audit(
            db,
            actor_id=user.id,
            action="sync_device_create",
            resource_type="sync_device",
            resource_id=item.id,
            detail=f"name={item.name} token_hint={item.token_hint}",
        )
        db.commit()
        db.refresh(item)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {**public_sync_service.serialize_device(item), "device_token": device_token}


@router.post(
    "/devices/{device_id}/rotate",
    response_model=schemas.SyncDeviceSecretResponse,
)
def rotate_device(
    device_id: int,
    expires_in_days: int = Form(public_sync_service.DEFAULT_DEVICE_TOKEN_DAYS, ge=1, le=365),
    db: Session = Depends(get_db),
    user=Depends(admin),
):
    item = _device_or_404(db, device_id)
    try:
        device_token = public_sync_service.rotate_device_credential(
            db,
            item,
            expires_in_days=expires_in_days,
        )
        add_admin_audit(
            db,
            actor_id=user.id,
            action="sync_device_rotate",
            resource_type="sync_device",
            resource_id=item.id,
            detail=f"name={item.name} token_hint={item.token_hint}",
        )
        db.commit()
        db.refresh(item)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {**public_sync_service.serialize_device(item), "device_token": device_token}


@router.post("/devices/{device_id}/revoke", response_model=schemas.SyncDeviceSummary)
def revoke_device(device_id: int, db: Session = Depends(get_db), user=Depends(admin)):
    item = _device_or_404(db, device_id)
    public_sync_service.revoke_device(db, item)
    add_admin_audit(
        db,
        actor_id=user.id,
        action="sync_device_revoke",
        resource_type="sync_device",
        resource_id=item.id,
        detail=f"name={item.name} token_hint={item.token_hint}",
    )
    db.commit()
    db.refresh(item)
    return public_sync_service.serialize_device(item)


@router.get("/dashboard", response_model=schemas.SyncDashboardResponse)
def dashboard(db: Session = Depends(get_db), user=Depends(admin)):
    return public_sync_service.dashboard_payload(db)


def _update_device_flag(db, item, user, *, action: str, detail: str):
    add_admin_audit(
        db,
        actor_id=user.id,
        action=action,
        resource_type="sync_device",
        resource_id=item.id,
        detail=detail,
    )
    db.commit()
    db.refresh(item)
    return public_sync_service.serialize_device(item)


@router.post("/devices/{device_id}/pause", response_model=schemas.SyncDeviceSummary)
def pause(device_id: int, db: Session = Depends(get_db), user=Depends(admin)):
    item = _device_or_404(db, device_id)
    item.is_paused = True
    return _update_device_flag(
        db, item, user, action="sync_device_pause", detail=f"name={item.name}"
    )


@router.post("/devices/{device_id}/resume", response_model=schemas.SyncDeviceSummary)
def resume(device_id: int, db: Session = Depends(get_db), user=Depends(admin)):
    item = _device_or_404(db, device_id)
    item.is_paused = False
    return _update_device_flag(
        db, item, user, action="sync_device_resume", detail=f"name={item.name}"
    )


@router.post("/devices/{device_id}/scan", response_model=schemas.SyncDeviceSummary)
def request_scan(device_id: int, db: Session = Depends(get_db), user=Depends(admin)):
    item = _device_or_404(db, device_id)
    if item.revoked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "已撤销设备不能请求扫描")
    item.scan_requested = True
    return _update_device_flag(
        db, item, user, action="sync_device_scan", detail=f"name={item.name}"
    )


@router.post("/heartbeat")
def heartbeat(db: Session = Depends(get_db), item=Depends(device)):
    requested = item.scan_requested
    item.scan_requested = False
    db.commit()
    return {"device_id": item.id, "is_paused": item.is_paused, "scan_requested": requested}


@router.post("/files", response_model=schemas.SyncFileSummary)
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


@router.post("/files/chunks", response_model=schemas.SyncFileSummary)
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


@router.post("/errors")
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


@router.delete("/files")
def remove(relative_path: str, db: Session = Depends(get_db), item=Depends(device)):
    try:
        public_sync_service.delete_file(db, item, relative_path)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"deleted": True, "relative_path": public_sync_service.safe_relative_path(relative_path)}
