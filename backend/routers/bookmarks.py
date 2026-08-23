import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List, Literal, Optional

import bookmark_service
import models
import schemas
from database import get_db
from dependencies import get_current_user

router = APIRouter(tags=["bookmarks"])


def bookmark_backup_output_dir() -> Path:
    configured = os.getenv("BOOKMARK_BACKUP_OUTPUT_DIR")
    if configured:
        return Path(configured)

    backup_root = os.getenv("BACKUP_OUTPUT_DIR")
    if backup_root:
        return Path(backup_root) / "bookmarks"

    return Path(__file__).resolve().parents[2] / "backups" / "bookmarks"


def model_updates(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)


def serialize_bookmark(bookmark: models.Bookmark) -> dict:
    return {
        "id": bookmark.id,
        "user_id": bookmark.user_id,
        "folder_id": bookmark.folder_id,
        "title": bookmark.title,
        "url": bookmark.url,
        "description": bookmark.description,
        "favicon": bookmark.favicon,
        "preview_url": bookmark.preview_url,
        "sort_order": bookmark.sort_order,
        "is_archived": bookmark.is_archived,
        "is_public": bookmark.is_public,
        "is_pinned": bookmark.is_pinned,
        "visit_count": bookmark.visit_count,
        "show_description": bookmark.show_description,
        "show_preview": bookmark.show_preview,
        "show_visit_count": bookmark.show_visit_count,
        "allow_indexing": bookmark.allow_indexing,
        "tags": bookmark_service.tags_for_bookmark(bookmark),
        "created_at": bookmark.created_at,
        "updated_at": bookmark.updated_at,
        "last_visited_at": bookmark.last_visited_at,
    }


@router.get(
    "/public/collection",
    response_model=schemas.PublicCollectionResponse,
)
def get_public_collection(
    q: Optional[str] = Query(default=None, max_length=200),
    folder_id: Optional[int] = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    bookmarks = bookmark_service.public_bookmarks(
        db,
        query=q,
        folder_id=folder_id,
        limit=limit,
    )
    serialized = [
        bookmark_service.serialize_public_bookmark(bookmark)
        for bookmark in bookmarks
    ]
    folders = [
        {
            "id": folder.id,
            "name": folder.name,
            "icon": folder.icon,
            "color": folder.color,
        }
        for folder in bookmark_service.public_folders(db)
    ]
    return {
        "bookmarks": serialized,
        "folders": folders,
    }


@router.get("/bookmark-folders", response_model=List[schemas.BookmarkFolderInfo])
def list_bookmark_folders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return db.query(models.BookmarkFolder).filter(
        models.BookmarkFolder.user_id == current_user.id,
    ).order_by(models.BookmarkFolder.sort_order, models.BookmarkFolder.id).all()


@router.post("/bookmark-folders", response_model=schemas.BookmarkFolderInfo)
def create_bookmark_folder(
    folder: schemas.BookmarkFolderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        return bookmark_service.create_folder(
            db,
            user_id=current_user.id,
            name=folder.name,
            parent_id=folder.parent_id,
            icon=folder.icon,
            color=folder.color,
            sort_order=folder.sort_order,
            is_sensitive=folder.is_sensitive,
            is_public=folder.is_public,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/bookmark-folders/{folder_id}", response_model=schemas.BookmarkFolderInfo)
def update_bookmark_folder(
    folder_id: int,
    folder: schemas.BookmarkFolderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    updates = model_updates(folder)
    try:
        db_folder = bookmark_service.update_folder(
            db,
            user_id=current_user.id,
            folder_id=folder_id,
            **updates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not db_folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return db_folder


@router.delete("/bookmark-folders/{folder_id}")
def delete_bookmark_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    success = bookmark_service.delete_folder(db, current_user.id, folder_id)
    if not success:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    return {"status": "success"}


@router.get("/bookmarks", response_model=List[schemas.BookmarkInfo])
def list_bookmarks(
    q: Optional[str] = Query(default=None, max_length=200),
    folder_id: Optional[int] = Query(default=None, gt=0),
    sort: Literal["manual", "recent", "popular", "newest"] = "manual",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return [
        serialize_bookmark(bookmark)
        for bookmark in bookmark_service.search_bookmarks(
            db,
            current_user.id,
            q,
            folder_id=folder_id,
            sort_by=sort,
        )
    ]


@router.post("/bookmarks", response_model=schemas.BookmarkInfo)
def create_bookmark(
    bookmark: schemas.BookmarkCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        db_bookmark = bookmark_service.create_bookmark(
            db,
            user_id=current_user.id,
            title=bookmark.title,
            url=bookmark.url,
            folder_id=bookmark.folder_id,
            description=bookmark.description,
            favicon=bookmark.favicon,
            preview_url=bookmark.preview_url,
            tag_names=bookmark.tags,
            sort_order=bookmark.sort_order,
            is_public=bookmark.is_public,
            is_pinned=bookmark.is_pinned,
            show_description=bookmark.show_description,
            show_preview=bookmark.show_preview,
            show_visit_count=bookmark.show_visit_count,
            allow_indexing=bookmark.allow_indexing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_bookmark(db_bookmark)


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


@router.post("/bookmarks/bulk", response_model=schemas.BookmarkBulkResult)
def bulk_update_bookmarks(
    action: schemas.BookmarkBulkAction,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        return bookmark_service.bulk_update_bookmarks(
            db,
            user_id=current_user.id,
            bookmark_ids=action.ids,
            action=action.action,
            folder_id=action.folder_id,
            ordered_ids=action.ordered_ids,
        )
    except ValueError as exc:
        status_code = 404 if str(exc) == "所选收藏不可用" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post(
    "/bookmarks/{bookmark_id}/visit",
    response_model=schemas.BookmarkInfo,
)
def visit_bookmark(
    bookmark_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    bookmark = bookmark_service.record_bookmark_visit(
        db,
        current_user.id,
        bookmark_id,
    )
    if not bookmark:
        raise HTTPException(status_code=404, detail="收藏不存在")
    return serialize_bookmark(bookmark)


@router.get("/search-engines", response_model=List[schemas.SearchEngineInfo])
def list_search_engines(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return bookmark_service.list_search_engines(db, current_user.id)


@router.post("/search-engines", response_model=schemas.SearchEngineInfo)
def create_search_engine(
    payload: schemas.SearchEngineCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return bookmark_service.create_search_engine(
        db,
        current_user.id,
        **model_updates(payload),
    )


@router.put(
    "/search-engines/{engine_id}",
    response_model=schemas.SearchEngineInfo,
)
def update_search_engine(
    engine_id: int,
    payload: schemas.SearchEngineUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    engine = bookmark_service.update_search_engine(
        db,
        current_user.id,
        engine_id,
        model_updates(payload),
    )
    if not engine:
        raise HTTPException(status_code=404, detail="搜索引擎不存在")
    return engine


@router.delete("/search-engines/{engine_id}")
def delete_search_engine(
    engine_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not bookmark_service.delete_search_engine(
        db,
        current_user.id,
        engine_id,
    ):
        raise HTTPException(status_code=404, detail="搜索引擎不存在")
    return {"status": "success"}


@router.put("/bookmarks/{bookmark_id}", response_model=schemas.BookmarkInfo)
def update_bookmark(
    bookmark_id: int,
    bookmark: schemas.BookmarkUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        db_bookmark = bookmark_service.update_bookmark(
            db,
            user_id=current_user.id,
            bookmark_id=bookmark_id,
            updates=model_updates(bookmark),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not db_bookmark:
        raise HTTPException(status_code=404, detail="收藏不存在")
    return serialize_bookmark(db_bookmark)


@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(
    bookmark_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    success = bookmark_service.delete_bookmark(db, current_user.id, bookmark_id)
    if not success:
        raise HTTPException(status_code=404, detail="收藏不存在")
    return {"status": "success"}
