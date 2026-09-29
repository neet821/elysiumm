"""Publish completed tus uploads into an owned transfer session."""

import secrets
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import models
import transfer_service
from tus_runtime import _publish_staged_file


def finalize_transfer_file_upload(
    db: Session,
    *,
    reservation: models.TusUploadReservation,
    source: Path,
    digest: str,
) -> tuple[dict, Path]:
    transfer_session = (
        db.query(models.TransferSession)
        .filter(models.TransferSession.id == reservation.transfer_session_id)
        .with_for_update()
        .first()
    )
    if transfer_session is None:
        raise HTTPException(status.HTTP_410_GONE, "中转会话已失效")
    stored_name = f"{secrets.token_hex(16)}.bin"
    root = transfer_service.ensure_storage().resolve()
    final_path = (root / stored_name).resolve()
    if final_path.parent != root:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "存储路径无效")

    try:
        _publish_staged_file(source, final_path)
        record = models.TransferFile(
            session_id=transfer_session.id,
            original_name=reservation.original_name,
            stored_name=stored_name,
            storage_path=str(final_path),
            file_size=reservation.upload_length,
            sha256=digest,
        )
        db.add(record)
        db.flush()
        transfer_session.total_bytes += reservation.upload_length
        transfer_service.refresh_expiry(transfer_session)
        rotated_token = transfer_service.new_token()
        transfer_session.token_hash = transfer_service.token_hash(rotated_token)
        transfer_session.public_token = rotated_token
        payload = {
            "id": record.id,
            "name": record.original_name,
            "size": record.file_size,
            "sha256": record.sha256,
            "token": rotated_token,
            "url": f"/api/transfers/{rotated_token}",
            "download_url": f"/api/transfers/{rotated_token}/files/{record.id}",
        }
        return payload, final_path
    except Exception:
        final_path.unlink(missing_ok=True)
        raise
