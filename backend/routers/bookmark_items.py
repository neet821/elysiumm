from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import bookmark_service
import models
import schemas
from database import get_db
from dependencies import get_current_user
from routers.bookmark_route_helpers import model_updates, serialize_bookmark

list_create_router = APIRouter()
activity_router = APIRouter()
update_delete_router = APIRouter()


@list_create_router.get("/bookmarks", response_model=List[schemas.BookmarkInfo])
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


@list_create_router.post("/bookmarks", response_model=schemas.BookmarkInfo)
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


@activity_router.post("/bookmarks/bulk", response_model=schemas.BookmarkBulkResult)
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


@activity_router.post(
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


@update_delete_router.put("/bookmarks/{bookmark_id}", response_model=schemas.BookmarkInfo)
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


@update_delete_router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(
    bookmark_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    success = bookmark_service.delete_bookmark(db, current_user.id, bookmark_id)
    if not success:
        raise HTTPException(status_code=404, detail="收藏不存在")
    return {"status": "success"}
