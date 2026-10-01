from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
import music_service
from catalog_domain import TrackAvailability
from database import get_db
from dependencies import get_current_user
from music import ProviderError
from music_provider_runtime import music_provider_registry


router = APIRouter()


class TrackReference(BaseModel):
    provider: str = Field(default="audius", max_length=30)
    provider_track_id: str = Field(min_length=1, max_length=120)


@router.get("/favorites")
def favorites(db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = db.query(models.MusicFavorite).filter_by(user_id=user.id).order_by(models.MusicFavorite.created_at.desc()).all()
    return [music_service.favorite_payload(item) for item in items]


@router.post("/favorites")
async def add_favorite(payload: TrackReference, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if payload.provider != "audius":
        raise HTTPException(400, "自定义音源暂不支持收藏")
    existing = db.query(models.MusicFavorite).filter_by(
        user_id=user.id, provider=payload.provider, provider_track_id=payload.provider_track_id
    ).first()
    if existing:
        return music_service.favorite_payload(existing)
    adapter = music_provider_registry.get(payload.provider)
    get_track = getattr(adapter, "get_track", None)
    if adapter is None or not callable(get_track):
        raise HTTPException(503, "该曲库来源暂不支持收藏")
    try:
        track = await get_track(payload.provider_track_id)
    except (ProviderError, ValueError) as exc:
        raise HTTPException(502, "歌曲信息获取失败") from exc
    if track is None or track.availability is TrackAvailability.UNAVAILABLE:
        raise HTTPException(409, "这首歌暂时不允许在线播放")
    item = models.MusicFavorite(
        user_id=user.id,
        provider=track.provider,
        provider_track_id=track.provider_track_id,
        title=track.title,
        artist=track.artist,
        album=track.album,
        artwork_url=track.artwork_url,
        duration_seconds=track.duration_seconds,
        source_url=track.metadata.get("source_url"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return music_service.favorite_payload(item)


@router.delete("/favorites/{provider}/{track_id}")
def remove_favorite(provider: str, track_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.query(models.MusicFavorite).filter_by(
        user_id=user.id, provider=provider, provider_track_id=track_id
    ).first()
    if not item:
        raise HTTPException(404, "收藏不存在")
    db.delete(item)
    db.commit()
    return {"message": "已取消收藏"}
