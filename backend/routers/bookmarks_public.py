from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import bookmark_service
import schemas
from database import get_db

router = APIRouter()


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
