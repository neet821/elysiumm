from typing import Literal
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
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


def obsidian_metadata_access(
    x_obsidian_metadata_token: str | None = Header(default=None),
) -> None:
    configured = config.OBSIDIAN_METADATA_TOKEN
    if not configured:
        raise HTTPException(status_code=503, detail="Obsidian 资料接口尚未配置")
    if not x_obsidian_metadata_token or not secrets.compare_digest(
        x_obsidian_metadata_token, configured
    ):
        raise HTTPException(status_code=401, detail="资料接口凭据无效")


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


def _metadata_client() -> media_metadata_service.MediaMetadataClient:
    return media_metadata_service.MediaMetadataClient(
        tmdb_token=config.TMDB_API_READ_TOKEN,
        google_books_api_key=config.GOOGLE_BOOKS_API_KEY,
        igdb_client_id=config.IGDB_CLIENT_ID,
        igdb_client_secret=config.IGDB_CLIENT_SECRET,
        user_agent=config.METADATA_REQUEST_USER_AGENT,
        timeout_seconds=config.METADATA_REQUEST_TIMEOUT_SECONDS,
        mineradio_base_url=config.MUSIC_PROVIDER_BASE_URL,
        mineradio_admin_token=config.MUSIC_PROVIDER_ADMIN_TOKEN,
    )


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
    client = _metadata_client()
    return await client.search(payload.kind, payload.query)


@router.get("/api/admin/media/cover/{kind}/{source}/{source_id}")
async def get_media_cover(
    kind: Literal["book", "movie", "album", "game"],
    source: str,
    source_id: str,
    _current_user: models.User = Depends(administrator),
):
    client = _metadata_client()
    result = await client.fetch_cover(kind, source, source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="封面不存在或资料服务不可用")
    content, media_type = result
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/api/obsidian/media/search", response_model=schemas.MediaSearchResponse)
async def search_media_metadata_for_obsidian(
    payload: schemas.MediaSearchRequest,
    _: None = Depends(obsidian_metadata_access),
):
    return await _metadata_client().search(payload.kind, payload.query)


@router.get("/api/obsidian/media/cover/{kind}/{source}/{source_id}")
async def get_media_cover_for_obsidian(
    kind: Literal["book", "movie", "album", "game"],
    source: str,
    source_id: str,
    _: None = Depends(obsidian_metadata_access),
):
    result = await _metadata_client().fetch_cover(kind, source, source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="封面不存在或资料服务不可用")
    content, media_type = result
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


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
