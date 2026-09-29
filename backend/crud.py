from sqlalchemy.orm import Session, joinedload
from typing import Optional
import models
import schemas
import security as security
from account_crud import (
    create_user as create_user,
    delete_user as delete_user,
    get_all_users as get_all_users,
    get_user_by_email as get_user_by_email,
    get_user_by_id as get_user_by_id,
    get_user_by_username as get_user_by_username,
    update_user as update_user,
    update_user_password as update_user_password,
)
from content_crud import (
    create_post as create_post,
    create_tag as create_tag,
    delete_post as delete_post,
    generate_unique_slug as generate_unique_slug,
    get_all_tags as get_all_tags,
    get_post_by_id as get_post_by_id,
    get_post_by_slug as get_post_by_slug,
    get_posts as get_posts,
    get_tag_by_name as get_tag_by_name,
    increment_post_views as increment_post_views,
    slugify_value as slugify_value,
    update_post as update_post,
)
from link_crud import (
    create_category as create_category,
    create_link as create_link,
    delete_category as delete_category,
    delete_link as delete_link,
    get_all_links as get_all_links,
    get_categories_by_user as get_categories_by_user,
    get_category_by_id as get_category_by_id,
    get_link_by_id as get_link_by_id,
    get_links_by_user as get_links_by_user,
    update_category as update_category,
    update_link as update_link,
)
from gallery_crud import (
    create_photo as create_photo,
    delete_photo as delete_photo,
    get_photos as get_photos,
    update_photo as update_photo,
)
from message_board_crud import (
    create_message_board_entry as create_message_board_entry,
    delete_message as delete_message,
    get_message_board_entries as get_message_board_entries,
    like_message as like_message,
)

# Resource Request CRUD
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
