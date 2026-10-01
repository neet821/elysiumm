"""管理员使用的公开同步设备管理接口。"""

from fastapi import APIRouter, Depends, Form, HTTPException, status
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
