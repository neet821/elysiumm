import hashlib
import os
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath

import models
from config import config

SYNC_STORAGE_ROOT = config.PUBLIC_SYNC_STORAGE_DIR
MAX_SYNC_FILE_SIZE = config.MAX_PUBLIC_SYNC_FILE_SIZE
MAX_SYNC_CHUNK_SIZE = config.MAX_PUBLIC_SYNC_CHUNK_SIZE
MAX_SYNC_DEVICE_BYTES = config.MAX_PUBLIC_SYNC_DEVICE_BYTES
UPLOAD_TTL_SECONDS = config.PUBLIC_SYNC_UPLOAD_TTL_SECONDS
STREAM_BLOCK_SIZE = 1024 * 1024
MAX_TOTAL_CHUNKS = 100000


def safe_relative_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("只允许 Public 目录内的相对路径")
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 1000
        or value.startswith("/")
        or path == PurePosixPath(".")
        or path.is_absolute()
        or ".." in path.parts
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("只允许 Public 目录内的相对路径")
    return path.as_posix()


def _storage_root() -> Path:
    root = Path(SYNC_STORAGE_ROOT).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _destination_path(device_id: int, relative_path: str) -> Path:
    root = _storage_root()
    device_root = root / str(device_id)
    device_root.mkdir(parents=True, exist_ok=True)
    destination = (device_root / relative_path).resolve(strict=False)
    if not destination.is_relative_to(device_root.resolve()):
        raise ValueError("同步路径超出允许范围")
    return destination


def _normalize_sha256(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    normalized = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("SHA-256 格式无效")
    return normalized


def _validate_expected_size(value: int) -> int:
    if value < 0:
        raise ValueError("文件大小不能为负数")
    if value > MAX_SYNC_FILE_SIZE:
        raise ValueError("文件超过同步大小限制")
    return value


def _stream_to_path(stream, path: Path, *, limit: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("wb") as output:
            while chunk := stream.read(STREAM_BLOCK_SIZE):
                size += len(chunk)
                if size > limit:
                    raise ValueError("上传内容超过允许大小")
                output.write(chunk)
                digest.update(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return size, digest.hexdigest()


def _remove_empty_parents(path: Path, stop: Path) -> None:
    current = path
    while current != stop and current.is_relative_to(stop):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _atomic_replace(source: Path, destination: Path) -> Path | None:
    backup = None
    if destination.is_file():
        backup = destination.parent / f".{destination.name}.{secrets.token_hex(8)}.backup"
        try:
            os.link(destination, backup)
        except OSError:
            shutil.copy2(destination, backup)
    try:
        os.replace(source, destination)
    except Exception:
        if backup is not None:
            backup.unlink(missing_ok=True)
        raise
    return backup


def _rollback_replace(destination: Path, backup: Path | None) -> None:
    if backup is None:
        destination.unlink(missing_ok=True)
    else:
        os.replace(backup, destination)


def _active_uploads(db, device_id: int):
    return (
        db.query(models.SyncUpload)
        .filter_by(device_id=device_id, status="uploading")
        .all()
    )


def _check_device_quota(
    db,
    device_id: int,
    relative_path: str,
    expected_size: int,
    *,
    exclude_upload_id: int | None = None,
) -> None:
    projected = {
        item.relative_path: item.file_size
        for item in db.query(models.SyncFile)
        .filter(
            models.SyncFile.device_id == device_id,
            models.SyncFile.sync_status != "deleted",
        )
        .all()
    }
    for upload in _active_uploads(db, device_id):
        if upload.id != exclude_upload_id:
            projected[upload.relative_path] = upload.expected_size
    projected[relative_path] = expected_size
    if sum(projected.values()) > MAX_SYNC_DEVICE_BYTES:
        raise ValueError("设备同步空间配额不足")


def _file_record(db, device_id: int, relative_path: str):
    return (
        db.query(models.SyncFile)
        .filter_by(device_id=device_id, relative_path=relative_path)
        .first()
    )


def _publish_record(
    db,
    device,
    relative_path: str,
    destination: Path,
    *,
    size: int,
    digest: str,
    mtime: datetime | None,
    record=None,
):
    if record is None:
        record = _file_record(db, device.id, relative_path)
    if not record:
        record = models.SyncFile(
            device_id=device.id,
            relative_path=relative_path,
            file_name=PurePosixPath(relative_path).name,
        )
        db.add(record)
    record.file_size = size
    record.sha256 = digest
    record.mtime = mtime
    record.storage_path = str(destination)
    record.sync_status = "synced"
    record.bytes_transferred = size
    record.expected_size = size
    record.progress_percent = 100
    record.last_synced_at = datetime.utcnow()
    return record


def save_upload(
    db,
    device,
    relative_path: str,
    stream,
    mtime: datetime | None = None,
    *,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
):
    relative_path = safe_relative_path(relative_path)
    if device.is_paused:
        raise RuntimeError("同步已暂停")
    declared_size = _validate_expected_size(expected_size) if expected_size is not None else None
    declared_digest = _normalize_sha256(expected_sha256)
    if any(upload.relative_path == relative_path for upload in _active_uploads(db, device.id)):
        raise ValueError("该路径已有分块上传进行中")

    root = _storage_root()
    temp_path = root / ".tmp" / str(device.id) / f"{secrets.token_hex(16)}.upload"
    try:
        size, digest = _stream_to_path(stream, temp_path, limit=MAX_SYNC_FILE_SIZE)
        if declared_size is not None and size != declared_size:
            raise ValueError("上传文件大小与声明不一致")
        if declared_digest is not None and digest != declared_digest:
            raise ValueError("上传文件摘要与声明不一致")
        _check_device_quota(db, device.id, relative_path, size)
        destination = _destination_path(device.id, relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup = _atomic_replace(temp_path, destination)
        record = _publish_record(
            db,
            device,
            relative_path,
            destination,
            size=size,
            digest=digest,
            mtime=mtime,
        )
        db.add(models.SyncEvent(
            device_id=device.id,
            relative_path=relative_path,
            event_type="upsert",
            bytes_transferred=size,
        ))
        try:
            db.commit()
        except Exception:
            db.rollback()
            _rollback_replace(destination, backup)
            raise
        if backup is not None:
            backup.unlink(missing_ok=True)
        db.refresh(record)
        return record
    finally:
        temp_path.unlink(missing_ok=True)
        _remove_empty_parents(temp_path.parent, root)


def delete_file(db, device, relative_path: str):
    relative_path = safe_relative_path(relative_path)
    if device.is_paused:
        raise RuntimeError("同步已暂停")
    record = _file_record(db, device.id, relative_path)
    destination = _destination_path(device.id, relative_path)
    if record and destination.is_file():
        destination.unlink()
        record.sync_status = "deleted"
        record.last_synced_at = datetime.utcnow()
    db.add(models.SyncEvent(
        device_id=device.id,
        relative_path=relative_path,
        event_type="delete",
    ))
    db.commit()
    return record
