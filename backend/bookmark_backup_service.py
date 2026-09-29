import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

import bookmark_import_validation
import models
from bookmark_export_service import export_bookmarks_json


class BookmarkBackupValidationError(ValueError):
    pass


def list_bookmark_backups(db: Session, user_id: int):
    return db.query(models.BookmarkBackup).filter(
        models.BookmarkBackup.user_id == user_id,
    ).order_by(models.BookmarkBackup.created_at.desc()).all()


def bookmark_backup_output_dir() -> Path:
    configured = os.getenv("BOOKMARK_BACKUP_OUTPUT_DIR")
    if configured:
        return Path(configured)
    backup_root = os.getenv("BACKUP_OUTPUT_DIR")
    if backup_root:
        return Path(backup_root) / "bookmarks"
    return Path(__file__).resolve().parent.parent / "backups" / "bookmarks"


def create_bookmark_backup(
    db: Session,
    user_id: int,
    output_dir: Path,
) -> models.BookmarkBackup:
    from database_backup import build_backup_filename, sha256_file

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = export_bookmarks_json(
        db,
        user_id,
        record_job=False,
    )
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > bookmark_import_validation.MAX_IMPORT_BYTES:
        raise BookmarkBackupValidationError(
            "收藏数据过大，无法创建可恢复备份"
        )
    output_path = output_dir / build_backup_filename(
        f"bookmarks-user-{user_id}",
        ".json",
    )
    temporary_path = output_dir / f".{output_path.name}.{uuid4().hex}.tmp"
    committed = False
    try:
        with temporary_path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_path)
        backup = models.BookmarkBackup(
            user_id=user_id,
            file_path=str(output_path),
            file_size=output_path.stat().st_size,
            sha256=sha256_file(output_path),
        )
        db.add(backup)
        db.commit()
        committed = True
        db.refresh(backup)
        return backup
    except Exception:
        temporary_path.unlink(missing_ok=True)
        if not committed:
            output_path.unlink(missing_ok=True)
        db.rollback()
        raise


def serialize_bookmark_backup(backup: models.BookmarkBackup) -> dict[str, Any]:
    return {
        "id": backup.id,
        "filename": Path(backup.file_path).name,
        "file_size": backup.file_size,
        "sha256": backup.sha256,
        "created_at": backup.created_at,
    }
