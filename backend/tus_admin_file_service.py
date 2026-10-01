"""Publish completed tus uploads as administrator-managed files."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

import admin_file_service
import models
from admin_audit import add_admin_audit
from config import config
from tus_runtime import _publish_staged_file


def finalize_admin_file_upload(
    db: Session,
    *,
    reservation: models.TusUploadReservation,
    source: Path,
    digest: str,
) -> tuple[dict, Path]:
    root = Path(config.ADMIN_FILES_STORAGE_DIR).expanduser().resolve()
    _, extension = admin_file_service.validate_original_name(reservation.original_name)
    admin_file_service.validate_file_content(source, extension)
    stored_name = f"{uuid4().hex}{extension}"
    final_path = admin_file_service.resolve_private_path(root, stored_name)

    try:
        _publish_staged_file(source, final_path)
        record = models.AdminFile(
            original_name=reservation.original_name,
            stored_name=stored_name,
            content_type=reservation.content_type or "application/octet-stream",
            file_size=reservation.upload_length,
            sha256=digest,
            uploaded_by=reservation.owner_user_id,
        )
        db.add(record)
        db.flush()
        add_admin_audit(
            db,
            actor_id=reservation.owner_user_id,
            action="admin_file_upload",
            resource_type="admin_file",
            resource_id=record.id,
            detail=f"name={reservation.original_name} size={reservation.upload_length}",
        )
        payload = {
            "id": record.id,
            "name": record.original_name,
            "size": record.file_size,
            "content_type": record.content_type,
            "sha256": record.sha256,
            "download_url": f"/api/admin/files/{record.id}/download",
        }
        return payload, final_path
    except Exception:
        final_path.unlink(missing_ok=True)
        raise
