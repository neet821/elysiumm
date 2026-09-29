from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
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

# Link Category CRUD
def get_categories_by_user(db: Session, user_id: int):
    """获取用户的所有分类"""
    from sqlalchemy import func
    categories = db.query(
        models.LinkCategory,
        func.count(models.WebsiteLink.id).label('link_count')
    ).outerjoin(
        models.WebsiteLink
    ).filter(
        models.LinkCategory.user_id == user_id
    ).group_by(
        models.LinkCategory.id
    ).all()

    result = []
    for category, link_count in categories:
        category_dict = {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "user_id": category.user_id,
            "created_at": category.created_at,
            "link_count": link_count
        }
        result.append(category_dict)
    return result

def get_category_by_id(db: Session, category_id: int, user_id: int):
    """获取特定分类"""
    return db.query(models.LinkCategory).filter(
        models.LinkCategory.id == category_id,
        models.LinkCategory.user_id == user_id
    ).first()

def create_category(db: Session, category: schemas.LinkCategoryCreate, user_id: int):
    """创建分类"""
    db_category = models.LinkCategory(
        name=category.name,
        description=category.description,
        user_id=user_id
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def update_category(db: Session, category_id: int, category_update: schemas.LinkCategoryUpdate, user_id: int):
    """更新分类"""
    db_category = get_category_by_id(db, category_id, user_id)
    if not db_category:
        return None

    update_data = category_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_category, field, value)

    db.commit()
    db.refresh(db_category)
    return db_category

def delete_category(db: Session, category_id: int, user_id: int):
    """删除分类(级联删除该分类下的所有链接)"""
    db_category = get_category_by_id(db, category_id, user_id)
    if db_category:
        db.delete(db_category)
        db.commit()
        return True
    return False

# Website Link CRUD
def get_all_links(db: Session, category_id: Optional[int] = None):
    """获取所有链接(公开),可按分类筛选"""
    query = db.query(models.WebsiteLink)
    if category_id:
        query = query.filter(models.WebsiteLink.category_id == category_id)
    return query.order_by(models.WebsiteLink.created_at.desc()).all()

def get_links_by_user(db: Session, user_id: int, category_id: Optional[int] = None):
    """获取用户的链接,可按分类筛选. 同时包含所有管理员的链接(全局可见)"""
    # Join with User to check for admin role
    query = db.query(models.WebsiteLink).join(models.User).filter(
        or_(
            models.WebsiteLink.user_id == user_id,
            models.User.role == 'admin'
        )
    )
    if category_id:
        query = query.filter(models.WebsiteLink.category_id == category_id)
    return query.order_by(models.WebsiteLink.created_at.desc()).all()

def get_link_by_id(db: Session, link_id: int, user_id: int):
    """获取特定链接"""
    return db.query(models.WebsiteLink).filter(
        models.WebsiteLink.id == link_id,
        models.WebsiteLink.user_id == user_id
    ).first()

def create_link(db: Session, link: schemas.WebsiteLinkCreate, user_id: int):
    """创建链接"""
    db_link = models.WebsiteLink(
        title=link.title,
        url=link.url,
        description=link.description,
        category_id=link.category_id,
        user_id=user_id
    )
    db.add(db_link)
    db.commit()
    db.refresh(db_link)
    return db_link

def update_link(db: Session, link_id: int, link_update: schemas.WebsiteLinkUpdate, user_id: int):
    """更新链接"""
    db_link = get_link_by_id(db, link_id, user_id)
    if not db_link:
        return None

    update_data = link_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_link, field, value)

    db.commit()
    db.refresh(db_link)
    return db_link

def delete_link(db: Session, link_id: int, user_id: int):
    """删除链接"""
    db_link = get_link_by_id(db, link_id, user_id)
    if db_link:
        db.delete(db_link)
        db.commit()
        return True
    return False

# Photo CRUD
def get_photos(db: Session, skip: int = 0, limit: int = 100, featured_only: bool = False):
    query = db.query(models.Photo).options(joinedload(models.Photo.tags))
    if featured_only:
        query = query.filter(models.Photo.is_featured == True)
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
