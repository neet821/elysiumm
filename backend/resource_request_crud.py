"""Resource-request and reply persistence operations."""

from typing import Optional

from sqlalchemy.orm import Session, joinedload

import models
import schemas


def get_resource_requests(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None):
    query = db.query(models.ResourceRequest).options(joinedload(models.ResourceRequest.user), joinedload(models.ResourceRequest.replies).joinedload(models.WishlistReply.user))
    if status:
        query = query.filter(models.ResourceRequest.status == status)
    return query.order_by(models.ResourceRequest.created_at.desc()).offset(skip).limit(limit).all()


def create_resource_request(db: Session, request: schemas.ResourceRequestCreate, user_id: int):
    db_request = models.ResourceRequest(
        title=request.title,
        content=request.content,
        user_id=user_id,
        is_anonymous=request.is_anonymous,
        is_private=request.is_private
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request


def create_wishlist_reply(db: Session, reply: schemas.WishlistReplyCreate, request_id: int, user_id: int):
    db_reply = models.WishlistReply(
        content=reply.content,
        request_id=request_id,
        user_id=user_id
    )
    db.add(db_reply)
    db.commit()
    db.refresh(db_reply)
    return db_reply


def update_resource_request(db: Session, request_id: int, request_update: schemas.ResourceRequestUpdate):
    db_request = db.query(models.ResourceRequest).filter(models.ResourceRequest.id == request_id).first()
    if not db_request:
        return None

    update_data = request_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_request, field, value)

    db.commit()
    db.refresh(db_request)
    return db_request


def delete_resource_request(db: Session, request_id: int):
    db_request = db.query(models.ResourceRequest).filter(models.ResourceRequest.id == request_id).first()
    if db_request:
        db.delete(db_request)
        db.commit()
        return True
    return False
