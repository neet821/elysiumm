from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

import bookmark_service
import models
import schemas
from database import get_db
from dependencies import get_current_user
from bookmark_service import bookmark_backup_output_dir

router = APIRouter()


@router.get("/bookmarks/export/json")
def export_bookmarks_json(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return bookmark_service.export_bookmarks_json(db, current_user.id)


@router.post("/bookmarks/import/json", response_model=schemas.BookmarkImportJobInfo)
async def import_bookmarks_json(
    request: Request,
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        job = bookmark_service.import_bookmarks_json(
            db,
            current_user.id,
            await request.body(),
            dry_run=dry_run,
            backup_dir=bookmark_backup_output_dir(),
        )
    except bookmark_service.BookmarkImportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except bookmark_service.BookmarkImportExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return bookmark_service.serialize_import_job(job)


@router.get("/bookmarks/export/html")
def export_bookmarks_html(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return Response(
        bookmark_service.export_bookmarks_html(db, current_user.id),
        media_type="text/html",
        headers={"Content-Disposition": 'attachment; filename="bookmarks.html"'},
    )


@router.post("/bookmarks/import/html", response_model=schemas.BookmarkImportJobInfo)
async def import_bookmarks_html(
    request: Request,
    dry_run: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        job = bookmark_service.import_bookmarks_html(
            db,
            current_user.id,
            await request.body(),
            dry_run=dry_run,
            backup_dir=bookmark_backup_output_dir(),
        )
    except bookmark_service.BookmarkImportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except bookmark_service.BookmarkImportExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return bookmark_service.serialize_import_job(job)


@router.get("/bookmarks/backups", response_model=List[schemas.BookmarkBackupInfo])
def list_bookmark_backups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return [
        bookmark_service.serialize_bookmark_backup(backup)
        for backup in bookmark_service.list_bookmark_backups(db, current_user.id)
    ]


@router.post("/bookmarks/backups", response_model=schemas.BookmarkBackupInfo)
def create_bookmark_backup(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        backup = bookmark_service.create_bookmark_backup(
            db,
            current_user.id,
            bookmark_backup_output_dir(),
        )
    except bookmark_service.BookmarkBackupValidationError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return bookmark_service.serialize_bookmark_backup(backup)


@router.post(
    "/bookmarks/backups/{backup_id}/restore",
    response_model=schemas.BookmarkImportJobInfo,
)
def restore_bookmark_backup(
    backup_id: int,
    request: schemas.BookmarkRestoreRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        job = bookmark_service.restore_bookmark_backup(
            db,
            current_user.id,
            backup_id,
            replace_existing=request.replace_existing,
            backup_root=bookmark_backup_output_dir(),
        )
    except bookmark_service.BookmarkBackupValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except bookmark_service.BookmarkImportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except bookmark_service.BookmarkImportExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="收藏备份不存在")
    return bookmark_service.serialize_import_job(job)
