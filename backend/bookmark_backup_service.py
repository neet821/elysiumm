import hmac
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

import bookmark_transfer_service
import bookmark_import_validation
import models


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
    payload = bookmark_transfer_service.export_bookmarks_json(
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


def _verified_backup_path(
    backup: models.BookmarkBackup,
    backup_root: Path,
) -> Path:
    from database_backup import sha256_file

    root = Path(backup_root).expanduser().resolve()
    try:
        path = Path(backup.file_path).expanduser().resolve(strict=True)
        path.relative_to(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise BookmarkBackupValidationError(
            "收藏备份位置无效"
        ) from exc
    if not path.is_file():
        raise BookmarkBackupValidationError("收藏备份文件无效")
    actual_size = path.stat().st_size
    if (
        actual_size != backup.file_size
        or actual_size > bookmark_import_validation.MAX_IMPORT_BYTES
    ):
        raise BookmarkBackupValidationError("收藏备份大小校验失败")
    if not backup.sha256 or not hmac.compare_digest(
        sha256_file(path),
        backup.sha256,
    ):
        raise BookmarkBackupValidationError("收藏备份摘要校验失败")
    return path


def restore_bookmark_backup(
    db: Session,
    user_id: int,
    backup_id: int,
    replace_existing: bool = False,
    *,
    backup_root: Path | None = None,
) -> models.BookmarkImportJob | None:
    backup = (
        db.query(models.BookmarkBackup)
        .filter(
            models.BookmarkBackup.id == backup_id,
            models.BookmarkBackup.user_id == user_id,
        )
        .first()
    )
    if not backup:
        return None

    root = backup_root or bookmark_backup_output_dir()
    backup_path = _verified_backup_path(backup, root)
    payload = backup_path.read_bytes()
    from bookmark_transfer_service import import_bookmarks_json

    return import_bookmarks_json(
        db,
        user_id,
        payload,
        backup_dir=Path(root),
        replace_existing=replace_existing,
        source_type="restore",
    )
