import hashlib
import json
import os
import re
import secrets
import shutil
from datetime import datetime, timedelta
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
DEFAULT_DEVICE_TOKEN_DAYS = 90
MAX_DEVICE_TOKEN_DAYS = 365
MAX_DEVICE_TOKEN_LENGTH = 512
MAX_DASHBOARD_DEVICES = 200
MAX_DASHBOARD_FILES = 500
MAX_DASHBOARD_EVENTS = 100
INVALID_DEVICE_CREDENTIAL = "无效的同步设备凭据"


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validate_expiry_days(expires_in_days: int) -> int:
    if not 1 <= expires_in_days <= MAX_DEVICE_TOKEN_DAYS:
        raise ValueError("设备凭据有效期必须为 1 到 365 天")
    return expires_in_days


def _new_device_token() -> str:
    return secrets.token_urlsafe(32)


def create_device(
    db,
    *,
    name: str,
    expires_in_days: int = DEFAULT_DEVICE_TOKEN_DAYS,
    now: datetime | None = None,
):
    normalized_name = " ".join(name.split())
    if not normalized_name or len(normalized_name) > 100 or any(ord(char) < 32 for char in name):
        raise ValueError("设备名称必须为 1 到 100 个可见字符")
    days = _validate_expiry_days(expires_in_days)
    current_time = now or datetime.utcnow()
    token = _new_device_token()
    item = models.SyncDevice(
        name=normalized_name,
        device_token_hash=hash_device_token(token),
        token_hint=token[-4:],
        token_expires_at=current_time + timedelta(days=days),
        status="offline",
    )
    db.add(item)
    db.flush()
    return item, token


def rotate_device_credential(
    db,
    item,
    *,
    expires_in_days: int = DEFAULT_DEVICE_TOKEN_DAYS,
    now: datetime | None = None,
) -> str:
    days = _validate_expiry_days(expires_in_days)
    current_time = now or datetime.utcnow()
    token = _new_device_token()
    item.device_token_hash = hash_device_token(token)
    item.token_hint = token[-4:]
    item.token_expires_at = current_time + timedelta(days=days)
    item.rotated_at = current_time
    item.revoked_at = None
    item.status = "offline"
    item.scan_requested = False
    db.flush()
    return token


def revoke_device(db, item, *, now: datetime | None = None):
    item.revoked_at = now or datetime.utcnow()
    item.status = "revoked"
    item.is_paused = True
    item.scan_requested = False
    db.flush()
    return item


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


def authenticate_device(db, token: str, *, now: datetime | None = None):
    if not isinstance(token, str) or not token or len(token) > MAX_DEVICE_TOKEN_LENGTH:
        raise ValueError(INVALID_DEVICE_CREDENTIAL)
    token_hash = hash_device_token(token)
    item = db.query(models.SyncDevice).filter(models.SyncDevice.device_token_hash == token_hash).first()
    current_time = now or datetime.utcnow()
    if (
        not item
        or item.revoked_at is not None
        or (item.token_expires_at is not None and item.token_expires_at <= current_time)
    ):
        raise ValueError(INVALID_DEVICE_CREDENTIAL)
    item.status = "online"
    item.last_seen_at = current_time
    db.commit()
    return item


def serialize_device(item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "token_hint": item.token_hint,
        "token_expires_at": item.token_expires_at,
        "revoked_at": item.revoked_at,
        "rotated_at": item.rotated_at,
        "root_name": item.root_name,
        "status": item.status,
        "is_paused": item.is_paused,
        "scan_requested": item.scan_requested,
        "last_seen_at": item.last_seen_at,
        "created_at": item.created_at,
    }


def serialize_file(item) -> dict:
    return {
        "id": item.id,
        "device_id": item.device_id,
        "relative_path": item.relative_path,
        "file_name": item.file_name,
        "file_size": item.file_size,
        "sha256": item.sha256,
        "mtime": item.mtime,
        "sync_status": item.sync_status,
        "bytes_transferred": item.bytes_transferred,
        "expected_size": item.expected_size,
        "progress_percent": item.progress_percent,
        "last_synced_at": item.last_synced_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def serialize_event(item) -> dict:
    return {
        "id": item.id,
        "device_id": item.device_id,
        "relative_path": item.relative_path,
        "event_type": item.event_type,
        "status": item.status,
        "bytes_transferred": item.bytes_transferred,
        "created_at": item.created_at,
    }


def dashboard_payload(db) -> dict:
    devices = (
        db.query(models.SyncDevice)
        .order_by(models.SyncDevice.created_at.desc(), models.SyncDevice.id.desc())
        .limit(MAX_DASHBOARD_DEVICES)
        .all()
    )
    files = (
        db.query(models.SyncFile)
        .filter(models.SyncFile.sync_status != "deleted")
        .order_by(models.SyncFile.relative_path, models.SyncFile.id)
        .limit(MAX_DASHBOARD_FILES)
        .all()
    )
    events = (
        db.query(models.SyncEvent)
        .order_by(models.SyncEvent.created_at.desc(), models.SyncEvent.id.desc())
        .limit(MAX_DASHBOARD_EVENTS)
        .all()
    )
    return {
        "devices": [serialize_device(item) for item in devices],
        "files": [serialize_file(item) for item in files],
        "events": [serialize_event(item) for item in events],
    }


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
):
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


def save_chunk(
    db,
    device,
    relative_path,
    upload_id,
    chunk_index,
    total_chunks,
    expected_size,
    stream,
    mtime=None,
    *,
    expected_sha256=None,
    now=None,
):
    relative_path = safe_relative_path(relative_path)
    if device.is_paused:
        raise RuntimeError("同步已暂停")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", upload_id):
        raise ValueError("分块参数无效")
    if not 0 <= chunk_index < total_chunks <= MAX_TOTAL_CHUNKS:
        raise ValueError("分块参数无效")
    expected_size = _validate_expected_size(expected_size)
    expected_sha256 = _normalize_sha256(expected_sha256)
    current_time = now or datetime.utcnow()
    cleanup_expired_uploads(db, now=current_time)

    session = (
        db.query(models.SyncUpload)
        .filter_by(device_id=device.id, upload_id=upload_id)
        .first()
    )
    if session:
        identity_matches = (
            session.relative_path == relative_path
            and session.expected_size == expected_size
            and session.expected_sha256 == expected_sha256
            and session.total_chunks == total_chunks
        )
        if not identity_matches:
            raise ValueError("上传编号已绑定其他文件或参数")
        if session.status == "completed":
            record = _file_record(db, device.id, relative_path)
            if (
                expected_sha256 is not None
                and record is not None
                and record.file_size == expected_size
                and record.sha256 == expected_sha256
            ):
                return record
            raise ValueError("已完成上传与当前文件不一致")
    else:
        _check_device_quota(db, device.id, relative_path, expected_size)
        chunk_root = _storage_root() / ".chunks" / str(device.id) / upload_id
        if chunk_root.exists():
            shutil.rmtree(chunk_root)
        chunk_root.mkdir(parents=True, exist_ok=False)
        session = models.SyncUpload(
            device_id=device.id,
            upload_id=upload_id,
            relative_path=relative_path,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            total_chunks=total_chunks,
            received_chunks=0,
            received_chunks_json="[]",
            received_bytes=0,
            status="uploading",
            temp_path=str(chunk_root),
            expires_at=current_time + timedelta(seconds=UPLOAD_TTL_SECONDS),
        )
        db.add(session)
        db.flush()

    _check_device_quota(
        db,
        device.id,
        relative_path,
        expected_size,
        exclude_upload_id=session.id,
    )
    chunk_root = Path(session.temp_path)
    expected_root = _storage_root() / ".chunks" / str(device.id) / upload_id
    if chunk_root.resolve(strict=False) != expected_root.resolve(strict=False):
        raise ValueError("上传临时路径无效")
    chunk_root.mkdir(parents=True, exist_ok=True)
    incoming = chunk_root / f".{chunk_index:08d}.{secrets.token_hex(8)}.incoming"
    part_path = chunk_root / f"{chunk_index:08d}.part"
    try:
        try:
            part_size, part_digest = _stream_to_path(
                stream,
                incoming,
                limit=MAX_SYNC_CHUNK_SIZE,
            )
        except Exception:
            _abort_upload(db, session)
            raise
        try:
            received_indexes = set(json.loads(session.received_chunks_json or "[]"))
        except (TypeError, ValueError):
            _abort_upload(db, session)
            raise ValueError("上传分块记录无效") from None
        if part_path.exists() or chunk_index in received_indexes:
            if not part_path.exists():
                incoming.unlink(missing_ok=True)
                _abort_upload(db, session)
                raise ValueError("上传分块记录与临时文件不一致")
            existing_digest = hashlib.sha256(part_path.read_bytes()).hexdigest()
            if part_path.stat().st_size != part_size or existing_digest != part_digest:
                raise ValueError("重复分块内容不一致")
            incoming.unlink(missing_ok=True)
        else:
            if session.received_bytes + part_size > expected_size:
                incoming.unlink(missing_ok=True)
                _abort_upload(db, session)
                raise ValueError("分块总大小超过声明值")
            os.replace(incoming, part_path)
            received_indexes.add(chunk_index)
            session.received_chunks_json = json.dumps(sorted(received_indexes))
            session.received_chunks = len(received_indexes)
            session.received_bytes += part_size
            session.updated_at = current_time
            session.expires_at = current_time + timedelta(seconds=UPLOAD_TTL_SECONDS)

        record = _file_record(db, device.id, relative_path)
        if not record:
            record = models.SyncFile(
                device_id=device.id,
                relative_path=relative_path,
                file_name=PurePosixPath(relative_path).name,
            )
            db.add(record)
        record.expected_size = expected_size
        record.bytes_transferred = session.received_bytes
        record.progress_percent = (
            min(99, int(session.received_bytes * 100 / expected_size))
            if expected_size
            else 0
        )
        record.sync_status = "uploading"
        record.mtime = mtime
        record.last_synced_at = current_time

        if received_indexes == set(range(total_chunks)):
            assembled = chunk_root / ".assembled"
            size = 0
            digest = hashlib.sha256()
            destination = None
            backup = None
            publication_active = False
            try:
                with assembled.open("wb") as output:
                    for index in range(total_chunks):
                        part = chunk_root / f"{index:08d}.part"
                        if not part.is_file():
                            raise ValueError("上传分块不完整")
                        with part.open("rb") as source:
                            while chunk := source.read(STREAM_BLOCK_SIZE):
                                size += len(chunk)
                                if size > MAX_SYNC_FILE_SIZE:
                                    raise ValueError("文件超过同步大小限制")
                                output.write(chunk)
                                digest.update(chunk)
                final_digest = digest.hexdigest()
                if size != expected_size:
                    raise ValueError("分块合并大小与声明不一致")
                if expected_sha256 is not None and final_digest != expected_sha256:
                    raise ValueError("分块合并摘要与声明不一致")
                destination = _destination_path(device.id, relative_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                backup = _atomic_replace(assembled, destination)
                publication_active = True
                record = _publish_record(
                    db,
                    device,
                    relative_path,
                    destination,
                    size=size,
                    digest=final_digest,
                    mtime=mtime,
                )
                session.status = "completed"
                session.received_bytes = size
                session.updated_at = current_time
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
                    publication_active = False
                    failed_session = (
                        db.query(models.SyncUpload)
                        .filter_by(device_id=device.id, upload_id=upload_id)
                        .first()
                    )
                    if failed_session is not None:
                        _abort_upload(db, failed_session)
                    raise
                publication_active = False
                if backup is not None:
                    backup.unlink(missing_ok=True)
                shutil.rmtree(chunk_root, ignore_errors=True)
                db.refresh(record)
                return record
            except Exception:
                if publication_active and destination is not None:
                    db.rollback()
                    _rollback_replace(destination, backup)
                assembled.unlink(missing_ok=True)
                current_session = (
                    db.query(models.SyncUpload)
                    .filter_by(device_id=device.id, upload_id=upload_id)
                    .first()
                )
                if current_session is not None:
                    _abort_upload(db, current_session)
                raise
        db.commit()
        db.refresh(record)
        return record
    except Exception:
        incoming.unlink(missing_ok=True)
        raise


def _restore_or_remove_upload_record(db, device_id: int, relative_path: str) -> None:
    record = _file_record(db, device_id, relative_path)
    if not record:
        return
    try:
        destination = _destination_path(device_id, relative_path)
    except ValueError:
        destination = None
    if destination is not None and destination.is_file():
        record.sync_status = "synced"
        record.bytes_transferred = record.file_size
        record.expected_size = record.file_size
        record.progress_percent = 100
    else:
        db.delete(record)


def _abort_upload(db, session) -> None:
    chunks_root = (_storage_root() / ".chunks").resolve()
    temp_path = Path(session.temp_path).resolve(strict=False)
    if temp_path.is_relative_to(chunks_root):
        shutil.rmtree(temp_path, ignore_errors=True)
        _remove_empty_parents(temp_path.parent, _storage_root())
    _restore_or_remove_upload_record(db, session.device_id, session.relative_path)
    db.delete(session)
    db.commit()


def cleanup_expired_uploads(db, *, now: datetime | None = None) -> int:
    current_time = now or datetime.utcnow()
    expired = (
        db.query(models.SyncUpload)
        .filter(models.SyncUpload.expires_at <= current_time)
        .all()
    )
    for session in expired:
        chunks_root = (_storage_root() / ".chunks").resolve()
        temp_path = Path(session.temp_path).resolve(strict=False)
        if temp_path.is_relative_to(chunks_root):
            shutil.rmtree(temp_path, ignore_errors=True)
            _remove_empty_parents(temp_path.parent, _storage_root())
        _restore_or_remove_upload_record(db, session.device_id, session.relative_path)
        db.delete(session)
    if expired:
        db.commit()
    return len(expired)


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
