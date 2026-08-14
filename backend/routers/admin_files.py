import hashlib
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import admin_file_service
import models
from admin_audit import add_admin_audit, commit_failed_admin_audit
from api_rate_limit import enforce_user_rate_limit, high_risk_rate_limiter
from config import config
from database import get_db
from dependencies import get_current_user


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


def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin" or not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


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
    temporary_path = None
    final_path = None
    published = False

    try:
        original_name, extension = admin_file_service.validate_original_name(
            file.filename
        )
        content_type = admin_file_service.validate_declared_content_type(
            extension,
            file.content_type,
        )

        storage_name = f"{uuid.uuid4().hex}{extension}"
        temporary_name = f"{uuid.uuid4().hex}.part"
        final_path = admin_file_service.resolve_private_path(root, storage_name)
        temporary_path = admin_file_service.resolve_private_path(root, temporary_name)

        digest = hashlib.sha256()
        file_size = 0
        with temporary_path.open("xb") as buffer:
            while True:
                chunk = await file.read(admin_file_service.CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > config.MAX_ADMIN_FILE_SIZE:
                    raise admin_file_service.AdminFileValidationError(
                        "文件超过大小限制",
                        status_code=413,
                        code="file_too_large",
                    )
                digest.update(chunk)
                buffer.write(chunk)
            buffer.flush()
            os.fsync(buffer.fileno())

        if file_size == 0:
            raise admin_file_service.AdminFileValidationError(
                "不能上传空文件",
                code="empty_file",
            )

        admin_file_service.validate_file_content(temporary_path, extension)
        os.replace(temporary_path, final_path)
        published = True

        record = models.AdminFile(
            original_name=original_name,
            stored_name=storage_name,
            content_type=content_type,
            file_size=file_size,
            sha256=digest.hexdigest(),
            uploaded_by=current_user.id,
        )
        db.add(record)
        db.flush()
        add_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_upload",
            resource_type="admin_file",
            resource_id=record.id,
            detail=f"name={original_name} size={file_size}",
        )
        db.commit()
        db.refresh(record)
        return serialize_file(record)
    except admin_file_service.AdminFileValidationError as exc:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        if published and final_path:
            final_path.unlink(missing_ok=True)
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_upload",
            resource_type="admin_file",
            detail=f"reason={exc.code}",
        )
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        if published and final_path:
            final_path.unlink(missing_ok=True)
        commit_failed_admin_audit(
            db,
            actor_id=current_user.id,
            action="admin_file_upload",
            resource_type="admin_file",
            detail="reason=storage_error",
        )
        raise HTTPException(status_code=500, detail="文件上传失败") from exc


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
