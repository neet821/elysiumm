import hmac
from pathlib import Path

from sqlalchemy.orm import Session

import bookmark_import_validation
import models
from bookmark_backup_service import (
    BookmarkBackupValidationError,
    bookmark_backup_output_dir,
)


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
