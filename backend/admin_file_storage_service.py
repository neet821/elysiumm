"""Private file upload persistence for the administrator Files workspace."""

import hashlib
import os
import uuid
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

import admin_file_service
import models
from admin_audit import add_admin_audit, commit_failed_admin_audit


class AsyncUpload(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


async def upload_admin_file(
    db: Session,
    file: AsyncUpload,
    *,
    actor_id: int,
    root: Path,
    max_size: int,
) -> models.AdminFile:
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
                if file_size > max_size:
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
            uploaded_by=actor_id,
        )
        db.add(record)
        db.flush()
        add_admin_audit(
            db,
            actor_id=actor_id,
            action="admin_file_upload",
            resource_type="admin_file",
            resource_id=record.id,
            detail=f"name={original_name} size={file_size}",
        )
        db.commit()
        db.refresh(record)
        return record
    except admin_file_service.AdminFileValidationError as exc:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        if published and final_path:
            final_path.unlink(missing_ok=True)
        commit_failed_admin_audit(
            db,
            actor_id=actor_id,
            action="admin_file_upload",
            resource_type="admin_file",
            detail=f"reason={exc.code}",
        )
        raise
    except Exception:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        if published and final_path:
            final_path.unlink(missing_ok=True)
        commit_failed_admin_audit(
            db,
            actor_id=actor_id,
            action="admin_file_upload",
            resource_type="admin_file",
            detail="reason=storage_error",
        )
        raise
