import hashlib
import json
import os
import re
import secrets
import shutil
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

import models
from public_sync_file_service import (
    MAX_SYNC_CHUNK_SIZE as MAX_SYNC_CHUNK_SIZE,
    MAX_SYNC_FILE_SIZE as MAX_SYNC_FILE_SIZE,
    MAX_TOTAL_CHUNKS as MAX_TOTAL_CHUNKS,
    STREAM_BLOCK_SIZE as STREAM_BLOCK_SIZE,
    UPLOAD_TTL_SECONDS as UPLOAD_TTL_SECONDS,
    _atomic_replace as _atomic_replace,
    _check_device_quota as _check_device_quota,
    _destination_path as _destination_path,
    _file_record as _file_record,
    _publish_record as _publish_record,
    _remove_empty_parents as _remove_empty_parents,
    _rollback_replace as _rollback_replace,
    _storage_root as _storage_root,
    _stream_to_path as _stream_to_path,
    _normalize_sha256 as _normalize_sha256,
    _validate_expected_size as _validate_expected_size,
    safe_relative_path as safe_relative_path,
)


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
                    record=record,
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
