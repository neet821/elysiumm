from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
import transfer_service
from transfer_download_service import (
    create_transfer_download_response as create_transfer_download_response,
)
from database import get_db
from dependencies import get_current_admin as admin_user
from transfer_session_service import (
    get_or_create_current_session as get_or_create_current_session,
    serialize_datetime as serialize_datetime,
    serialize_session as serialize_session,
)


router = APIRouter(tags=["transfers"])


class AdminTransferNotePayload(BaseModel):
    content: str = Field(default="", max_length=100_000)


@router.post("/api/admin/transfers", status_code=status.HTTP_201_CREATED)
def create_transfer(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    session, token = get_or_create_current_session(db, _admin.id)
    db.commit()
    db.refresh(session)
    return serialize_session(session, token)


@router.post("/api/admin/transfers/current-link")
def current_transfer_link(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    session, token = get_or_create_current_session(db, _admin.id)
    db.commit()
    db.refresh(session)
    return serialize_session(session, token)


@router.get("/api/admin/transfers")
def list_transfers(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    transfer_service.cleanup_expired(db)
    sessions = (
        db.query(models.TransferSession)
        .order_by(models.TransferSession.created_at.desc())
        .all()
    )
    return [serialize_session(session) for session in sessions]


@router.get("/api/admin/transfers/files")
def list_transfer_files(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    transfer_service.cleanup_expired(db)
    records = (
        db.query(models.TransferFile, models.TransferSession)
        .join(models.TransferSession, models.TransferFile.session_id == models.TransferSession.id)
        .order_by(models.TransferFile.created_at.desc(), models.TransferFile.id.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "name": item.original_name,
            "size": item.file_size,
            "sha256": item.sha256,
            "created_at": serialize_datetime(item.created_at),
            "transfer_id": session.id,
            "expires_at": serialize_datetime(session.expires_at),
            "download_url": f"/api/admin/transfers/files/{item.id}/download",
        }
        for item, session in records
    ]


def get_admin_transfer_note(db: Session) -> models.AdminTransferNote:
    note = db.query(models.AdminTransferNote).filter(models.AdminTransferNote.id == 1).first()
    if note is None:
        note = models.AdminTransferNote(id=1, content="")
        db.add(note)
        db.commit()
        db.refresh(note)
    return note


@router.get("/api/admin/transfers/note")
def read_admin_transfer_note(_admin: models.User = Depends(admin_user), db: Session = Depends(get_db)):
    return {"content": get_admin_transfer_note(db).content}


@router.put("/api/admin/transfers/note")
def write_admin_transfer_note(
    payload: AdminTransferNotePayload = Body(...),
    _admin: models.User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    note = get_admin_transfer_note(db)
    note.content = payload.content
    note.updated_by = _admin.id
    db.commit()
    return {"content": note.content}


@router.get("/api/admin/transfers/files/{file_id}/download")
def download_admin_transfer(
    file_id: int,
    request: Request,
    _admin: models.User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    transfer_service.cleanup_expired(db)
    item, session = (
        db.query(models.TransferFile, models.TransferSession)
        .join(models.TransferSession, models.TransferFile.session_id == models.TransferSession.id)
        .filter(models.TransferFile.id == file_id)
        .first()
        or (None, None)
    )
    if not item or session.expires_at <= transfer_service.utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在或已清理")
    return create_transfer_download_response(db, session, item, request)


@router.delete("/api/admin/transfers/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_transfer_file(
    file_id: int,
    _admin: models.User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    transfer_service.cleanup_expired(db)
    item, session = (
        db.query(models.TransferFile, models.TransferSession)
        .join(models.TransferSession, models.TransferFile.session_id == models.TransferSession.id)
        .filter(models.TransferFile.id == file_id)
        .first()
        or (None, None)
    )
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在或已清理")
    path = Path(item.storage_path).resolve()
    try:
        path.relative_to(transfer_service.ensure_storage())
    except ValueError:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "文件路径无效")
    path.unlink(missing_ok=True)
    session.total_bytes = max(0, session.total_bytes - item.file_size)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.delete("/api/admin/transfers/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer(
    session_id: int,
    _admin: models.User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    session = (
        db.query(models.TransferSession)
        .filter(models.TransferSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "中转链接不存在")
    transfer_service.delete_session_files(session)
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
