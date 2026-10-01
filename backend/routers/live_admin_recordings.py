from pathlib import Path
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import models
import schemas
from admin_audit import add_admin_audit
from config import config
from database import get_db
from live_recording_service import (
    UnsafeRecordingPath,
    delete_recording,
    resolve_recording_path,
)
from routers.live_admin_common import _rate_limit, active_administrator


router = APIRouter()


def _recording_payload(recording: models.LiveRecording) -> dict:
    return {
        "id": recording.id,
        "session_id": recording.session_id,
        "display_name": recording.display_name,
        "file_size": recording.file_size,
        "duration_seconds": recording.duration_seconds,
        "sha256": recording.sha256,
        "status": recording.status,
        "created_at": recording.created_at,
        "ready_at": recording.ready_at,
        "remote_provider": recording.remote_provider,
        "remote_file_id": recording.remote_file_id,
        "download_url": f"/api/admin/live/recordings/{recording.id}/download",
    }


@router.get("/recordings")
def list_recordings(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    rows = (
        db.query(models.LiveRecording)
        .order_by(models.LiveRecording.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_recording_payload(row) for row in rows]


def _get_recording(db: Session, recording_id: int) -> models.LiveRecording:
    recording = db.get(models.LiveRecording, recording_id)
    if recording is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "录像不存在")
    return recording


@router.get("/recordings/{recording_id}/download")
def download_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(active_administrator),
):
    recording = _get_recording(db, recording_id)
    try:
        path = resolve_recording_path(
            config.LIVE_RECORDING_ROOT,
            recording.relative_path,
        )
    except (UnsafeRecordingPath, FileNotFoundError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "录像文件不存在") from exc
    filename = re.sub(r"[^A-Za-z0-9._ -]+", "_", recording.display_name).strip()
    return FileResponse(path, filename=filename or f"recording-{recording.id}.mp4")


@router.put("/recordings/{recording_id}")
def update_recording(
    recording_id: int,
    payload: schemas.LiveRecordingUpdateRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    recording = _get_recording(db, recording_id)
    recording.display_name = payload.display_name.strip()
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_recording_update",
        resource_type="live_recording",
        resource_id=recording.id,
        detail="display name updated",
    )
    db.commit()
    db.refresh(recording)
    return _recording_payload(recording)


@router.delete("/recordings/{recording_id}")
def remove_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(active_administrator),
):
    _rate_limit(db, admin, "live_recording_delete", resource_id=recording_id)
    recording = _get_recording(db, recording_id)
    if recording.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "录像仍在处理中")
    try:
        deleted = delete_recording(
            db,
            recording=recording,
            recording_root=Path(config.LIVE_RECORDING_ROOT),
        )
    except UnsafeRecordingPath as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "录像路径无效") from exc
    add_admin_audit(
        db,
        actor_id=admin.id,
        action="live_recording_delete",
        resource_type="live_recording",
        resource_id=recording_id,
        outcome="success" if deleted else "missing",
        detail=f"file_deleted={deleted}",
    )
    db.commit()
    return {"deleted": deleted}
