from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import bookmark_service
import models
import schemas
from database import get_db
from dependencies import get_current_user
from routers.bookmark_route_helpers import model_updates

router = APIRouter()


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
