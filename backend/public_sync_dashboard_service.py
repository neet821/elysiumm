import models

MAX_DASHBOARD_DEVICES = 200
MAX_DASHBOARD_FILES = 500
MAX_DASHBOARD_EVENTS = 100


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
