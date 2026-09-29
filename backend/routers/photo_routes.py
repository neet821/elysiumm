"""Photo gallery endpoints and administrator-only image upload."""

import os
import shutil
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import crud
import models
import schemas
from config import config
from database import get_db
from dependencies import get_current_admin


router = APIRouter()


@router.get("/api/photos", response_model=list[schemas.Photo])
def get_photos(
    skip: int = 0,
    limit: int = 100,
    featured: bool = None,
    db: Session = Depends(get_db),
):
    """获取照片列表"""
    featured_only = featured if featured is not None else False
    photos = crud.get_photos(db, skip=skip, limit=limit, featured_only=featured_only)
    return photos


@router.post("/api/photos/upload")
async def upload_photo_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """上传照片文件(仅管理员)"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="文件必须是图片")

    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = config.UPLOAD_DIR / unique_filename

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail="图片上传失败") from e

    file_url = f"/uploads/{unique_filename}"
    return {"url": file_url, "filename": unique_filename}


@router.post(
    "/api/photos", response_model=schemas.Photo, status_code=status.HTTP_201_CREATED
)
def create_photo(
    photo: schemas.PhotoCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """创建照片(仅管理员)"""
    return crud.create_photo(db, photo)


@router.get("/api/photos/{photo_id}", response_model=schemas.Photo)
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    """获取单个照片详情"""
    photo = db.query(models.Photo).filter(models.Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return photo


@router.put("/api/photos/{photo_id}", response_model=schemas.Photo)
def update_photo(
    photo_id: int,
    photo_update: schemas.PhotoUpdate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """更新照片(仅管理员)"""
    updated_photo = crud.update_photo(db, photo_id, photo_update)
    if not updated_photo:
        raise HTTPException(status_code=404, detail="照片不存在")
    return updated_photo


@router.delete("/api/photos/{photo_id}")
def delete_photo(
    photo_id: int,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """删除照片(仅管理员)"""
    success = crud.delete_photo(db, photo_id)
    if not success:
        raise HTTPException(status_code=404, detail="照片不存在")
    return {"message": "照片已删除"}
