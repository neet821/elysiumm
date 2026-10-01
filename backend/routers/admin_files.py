import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import admin_file_service
import admin_file_storage_service
import models
from admin_audit import add_admin_audit, commit_failed_admin_audit
from api_rate_limit import (
    enforce_user_rate_limit,
    high_risk_rate_limiter as high_risk_rate_limiter,
)
from config import config
from database import get_db
from dependencies import get_current_admin


router = APIRouter(
    prefix="/api/admin/files",
    tags=["admin-files"],
    responses={404: {"description": "Not found"}},
)

ADMIN_FILE_UPLOAD_RATE_LIMIT_MAX = int(
    os.getenv("ADMIN_FILE_UPLOAD_RATE_LIMIT_MAX", "10")
)
ADMIN_FILE_UPLOAD_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("ADMIN_FILE_UPLOAD_RATE_LIMIT_WINDOW_SECONDS", "60")
)


def storage_root() -> Path:
    root = Path(config.ADMIN_FILES_STORAGE_DIR).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def serialize_file(record: models.AdminFile) -> dict:
    return {
        "id": record.id,
        "name": record.original_name,
        "size": record.file_size,
        "content_type": record.content_type,
        "sha256": record.sha256,
        "modified": record.created_at.isoformat(),
        "download_url": f"/api/admin/files/{record.id}/download",
    }


def get_file_record(db: Session, file_id: int) -> models.AdminFile | None:
    return db.query(models.AdminFile).filter(models.AdminFile.id == file_id).first()


@router.get("/")
def list_files(
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.AdminFile)
        .order_by(models.AdminFile.created_at.desc(), models.AdminFile.id.desc())
        .all()
    )
    return [serialize_file(record) for record in records]


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    enforce_user_rate_limit(
        db,
        actor_id=current_user.id,
        action="admin_file_upload",
        limit=ADMIN_FILE_UPLOAD_RATE_LIMIT_MAX,
        window_seconds=ADMIN_FILE_UPLOAD_RATE_LIMIT_WINDOW_SECONDS,
        resource_type="admin_file",
    )
    root = storage_root()
    try:
        record = await admin_file_storage_service.upload_admin_file(
            db,
            file,
            actor_id=current_user.id,
            root=root,
            max_size=config.MAX_ADMIN_FILE_SIZE,
        )
    except admin_file_service.AdminFileValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="文件上传失败") from exc
    return serialize_file(record)


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    record = get_file_record(db, file_id)
    if not record:
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_download",
            resource_type="admin_file",
            resource_id=file_id,
            detail="reason=not_found",
        )
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        path = admin_file_service.resolve_private_path(
            storage_root(),
            record.stored_name,
        )
    except admin_file_service.AdminFileValidationError as exc:
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_download",
            resource_type="admin_file",
            resource_id=file_id,
            detail=f"reason={exc.code}",
        )
        raise HTTPException(status_code=404, detail="文件不存在") from exc

    if not path.is_file():
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_download",
            resource_type="admin_file",
            resource_id=file_id,
            detail="reason=missing_storage",
        )
        raise HTTPException(status_code=404, detail="文件不存在")

    if admin_file_service.sha256_file(path) != record.sha256:
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_download",
            resource_type="admin_file",
            resource_id=file_id,
            detail="reason=checksum_mismatch",
        )
        raise HTTPException(status_code=409, detail="文件校验失败")

    add_admin_audit(
        db,
        actor_id=current_user.id,
        action="admin_file_download",
        resource_type="admin_file",
        resource_id=file_id,
        detail=f"name={record.original_name}",
    )
    db.commit()
    return FileResponse(
        path,
        filename=record.original_name,
        media_type=record.content_type,
    )


@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    record = get_file_record(db, file_id)
    if not record:
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_delete",
            resource_type="admin_file",
            resource_id=file_id,
            detail="reason=not_found",
        )
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        root = storage_root()
        path = admin_file_service.resolve_private_path(root, record.stored_name)
    except admin_file_service.AdminFileValidationError as exc:
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_delete",
            resource_type="admin_file",
            resource_id=file_id,
            detail=f"reason={exc.code}",
        )
        raise HTTPException(status_code=404, detail="文件不存在") from exc

    if not path.is_file():
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_delete",
            resource_type="admin_file",
            resource_id=file_id,
            detail="reason=missing_storage",
        )
        raise HTTPException(status_code=404, detail="文件不存在")

    tombstone = admin_file_service.resolve_private_path(
        root,
        f"{uuid.uuid4().hex}.trash",
    )
    os.replace(path, tombstone)
    try:
        original_name = record.original_name
        db.delete(record)
        add_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_delete",
            resource_type="admin_file",
            resource_id=file_id,
            detail=f"name={original_name}",
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        if tombstone.exists() and not path.exists():
            os.replace(tombstone, path)
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_delete",
            resource_type="admin_file",
            resource_id=file_id,
            detail="reason=database_error",
        )
        raise HTTPException(status_code=500, detail="文件删除失败") from exc

    tombstone.unlink(missing_ok=True)
    return {"status": "success", "id": file_id}
