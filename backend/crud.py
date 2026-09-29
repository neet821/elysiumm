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

def create_message_board_entry(db: Session, message: schemas.MessageBoardCreate, user_id: int):
    db_message = models.MessageBoard(
        content=message.content,
        user_id=user_id,
        parent_id=message.parent_id
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

def get_message_board_entries(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.MessageBoard)\
        .filter(models.MessageBoard.parent_id == None)\
        .options(joinedload(models.MessageBoard.user), joinedload(models.MessageBoard.replies).joinedload(models.MessageBoard.user))\
        .order_by(models.MessageBoard.created_at.desc())\
        .offset(skip).limit(limit).all()

def like_message(db: Session, message_id: int, user_id: int):
    # 检查是否已经点赞
    existing_like = db.query(models.MessageLike).filter(
        models.MessageLike.message_id == message_id,
        models.MessageLike.user_id == user_id
    ).first()

    if existing_like:
        # 如果已点赞，则取消点赞
        db.delete(existing_like)
        message = db.query(models.MessageBoard).filter(models.MessageBoard.id == message_id).first()
        if message:
            message.likes = max(0, message.likes - 1)
            db.commit()
            db.refresh(message)
            return message
    else:
        # 如果未点赞，则添加点赞
        new_like = models.MessageLike(message_id=message_id, user_id=user_id)
        db.add(new_like)
        message = db.query(models.MessageBoard).filter(models.MessageBoard.id == message_id).first()
        if message:
            message.likes += 1
            db.commit()
            db.refresh(message)
            return message

    return None

def delete_message(db: Session, message_id: int, user_id: int, is_admin: bool = False):
    """删除留言板消息，允许管理员或作者删除，并清理关联的点赞/子回复"""
    message = db.query(models.MessageBoard).filter(models.MessageBoard.id == message_id).first()
    if not message:
        return False, "留言不存在"

    if (not is_admin) and message.user_id != user_id:
        return False, "Permission denied"

    try:
        # 删除该消息及其子回复的点赞
        message_ids = [message.id]
        child_ids = [m.id for m in message.replies]
        message_ids.extend(child_ids)
        if message_ids:
            db.query(models.MessageLike).filter(models.MessageLike.message_id.in_(message_ids)).delete(synchronize_session=False)

        # 删除子回复
        for child in message.replies:
            db.delete(child)

        # 删除主消息
        db.delete(message)
        db.commit()
        return True, "Message deleted"
    except Exception as e:
        db.rollback()
        print(f"删除留言失败: {e}")
        return False, "Delete failed"

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
