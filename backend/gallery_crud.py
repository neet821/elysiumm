"""Photo gallery persistence operations."""

from sqlalchemy.orm import Session, joinedload

import models
import schemas
from content_crud import create_tag, get_tag_by_name


def get_photos(db: Session, skip: int = 0, limit: int = 100, featured_only: bool = False):
    query = db.query(models.Photo).options(joinedload(models.Photo.tags))
    if featured_only:
        query = query.filter(models.Photo.is_featured == True)  # noqa: E712
    return query.order_by(models.Photo.created_at.desc()).offset(skip).limit(limit).all()


def create_photo(db: Session, photo: schemas.PhotoCreate):
    # 处理标签
    tag_names = photo.tags
    tags = []
    for name in tag_names:
        tag = get_tag_by_name(db, name)
        if not tag:
            tag = create_tag(db, schemas.TagCreate(name=name))
        tags.append(tag)

    db_photo = models.Photo(
        url=photo.url,
        caption=photo.caption,
        location=photo.location,
        is_featured=photo.is_featured
    )
    db_photo.tags = tags

    db.add(db_photo)
    db.commit()
    db.refresh(db_photo)
    return db_photo


def update_photo(db: Session, photo_id: int, photo_update: schemas.PhotoUpdate):
    db_photo = db.query(models.Photo).filter(models.Photo.id == photo_id).first()
    if not db_photo:
        return None

    update_data = photo_update.dict(exclude_unset=True)

    # 处理标签更新
    if 'tags' in update_data:
        tag_names = update_data.pop('tags')
        tags = []
        for name in tag_names:
            tag = get_tag_by_name(db, name)
            if not tag:
                tag = create_tag(db, schemas.TagCreate(name=name))
            tags.append(tag)
        db_photo.tags = tags

    for field, value in update_data.items():
        setattr(db_photo, field, value)

    db.add(db_photo)
    db.commit()
    db.refresh(db_photo)
    return db_photo


def delete_photo(db: Session, photo_id: int):
    db_photo = db.query(models.Photo).filter(models.Photo.id == photo_id).first()
    if db_photo:
        db.delete(db_photo)
        db.commit()
        return True
    return False
