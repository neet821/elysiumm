from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import config
from database import get_db
from dependencies import get_current_user
import media_metadata_service
import media_service
import models
import schemas


router = APIRouter(tags=["media"])


def administrator(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, media_service.MediaNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (media_service.MediaDuplicate, IntegrityError)):
        raise HTTPException(status_code=409, detail="该来源资料已经保存") from exc
    if isinstance(exc, media_service.MediaRevisionConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, (media_service.MediaSourceMismatch, ValueError)):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/api/media/recent", response_model=schemas.MediaRecentResponse)
def get_recent_media(
    kind: Literal["book", "movie", "album", "game"] | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return media_service.public_recent(db, kind=kind, limit=limit)


@router.get("/api/media/{kind}/{entry_id}", response_model=schemas.MediaEntryView)
def get_public_media(
    kind: Literal["book", "movie", "album", "game"],
    entry_id: int,
    db: Session = Depends(get_db),
):
    if kind == "book":
        row = db.query(models.Book).filter(models.Book.id == entry_id, models.Book.is_public.is_(True)).first()
        if not row:
            raise HTTPException(status_code=404, detail="媒体不存在")
        return media_service.serialize_book_view(row)
    row = db.query(models.MediaEntry).filter(models.MediaEntry.id == entry_id, models.MediaEntry.kind == kind, models.MediaEntry.is_public.is_(True)).first()
    if not row:
        raise HTTPException(status_code=404, detail="媒体不存在")
    return media_service.serialize_media_view(row)


@router.post("/api/admin/media/search", response_model=schemas.MediaSearchResponse)
async def search_media_metadata(
    payload: schemas.MediaSearchRequest,
    _current_user: models.User = Depends(administrator),
):
    client = media_metadata_service.MediaMetadataClient(
        tmdb_token=config.TMDB_API_READ_TOKEN,
        user_agent=config.METADATA_REQUEST_USER_AGENT,
        timeout_seconds=config.METADATA_REQUEST_TIMEOUT_SECONDS,
        mineradio_base_url=config.MUSIC_PROVIDER_BASE_URL,
        mineradio_admin_token=config.MUSIC_PROVIDER_ADMIN_TOKEN,
    )
    return await client.search(payload.kind, payload.query)


@router.post(
    "/api/admin/media",
    response_model=schemas.MediaEntryAdminView,
    status_code=status.HTTP_201_CREATED,
)
def create_media_entry(
    payload: schemas.MediaCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        return media_service.create_media(db, payload, actor_id=current_user.id)
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)


@router.patch(
    "/api/admin/media/{kind}/{entry_id}",
    response_model=schemas.MediaMutationResult,
)
def patch_media_entry(
    kind: Literal["book", "movie", "album", "game"],
    entry_id: int,
    payload: schemas.MediaPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(administrator),
):
    try:
        return media_service.update_media(
            db,
            kind,
            entry_id,
            payload,
            actor_id=current_user.id,
        )
    except Exception as exc:
        db.rollback()
        _raise_service_error(exc)
