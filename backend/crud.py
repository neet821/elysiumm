from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from typing import Optional
import re
import uuid
import models, schemas, security

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = security.get_password_hash(user.password)

    # 检查是否是第一个用户,如果是则设为管理员
    user_count = db.query(models.User).count()
    role = "admin" if user_count == 0 else "user"

    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_all_users(db: Session, skip: int = 0, limit: int = 100):
    """获取所有用户(管理员功能)"""
    return db.query(models.User).offset(skip).limit(limit).all()

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate):
    """更新用户信息(管理员功能)"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None

    update_data = user_update.dict(exclude_unset=True)

    # 如果要更新密码,需要加密
    if "password" in update_data:
        update_data["hashed_password"] = security.get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_password(db: Session, user_id: int, old_password: str, new_password: str):
    """用户修改自己的密码"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None

    # 验证旧密码
    if not security.verify_password(old_password, db_user.hashed_password):
        return False

    # 更新密码
    db_user.hashed_password = security.get_password_hash(new_password)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    """删除用户(管理员功能) - 级联删除所有关联数据"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return False

    try:
        # 1. 删除用户的文章
        db.query(models.Post).filter(models.Post.author_id == user_id).delete()

        # 2. 删除用户的链接
        db.query(models.WebsiteLink).filter(models.WebsiteLink.user_id == user_id).delete()

        # 3. 删除用户的链接分类（会级联删除该分类下的所有链接）
        db.query(models.LinkCategory).filter(models.LinkCategory.user_id == user_id).delete()

        # 4. 删除用户的同步房间消息
        user_rooms = db.query(models.SyncRoom).filter(models.SyncRoom.host_user_id == user_id).all()
        for room in user_rooms:
            db.query(models.SyncRoomMessage).filter(models.SyncRoomMessage.room_id == room.id).delete()
            db.query(models.SyncRoomMember).filter(models.SyncRoomMember.room_id == room.id).delete()

        # 5. 删除用户的同步房间
        db.query(models.SyncRoom).filter(models.SyncRoom.host_user_id == user_id).delete()

        # 6. 删除用户作为成员的房间关系
        db.query(models.SyncRoomMember).filter(models.SyncRoomMember.user_id == user_id).delete()

        # 7. 删除用户发送的房间消息
        db.query(models.SyncRoomMessage).filter(models.SyncRoomMessage.user_id == user_id).delete()

        # 8. 最后删除用户
        db.delete(db_user)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"删除用户失败: {str(e)}")
        return False

# --- 标签 CRUD ---
def get_tag_by_name(db: Session, name: str):
    return db.query(models.Tag).filter(models.Tag.name == name).first()

def create_tag(db: Session, name: str, color: str = "#3B82F6"):
    db_tag = models.Tag(name=name, color=color)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

def get_all_tags(db: Session):
    return db.query(models.Tag).all()

# --- Slug helper functions ---
def slugify_value(value: str) -> str:
    """Create a URL friendly slug from the provided value.
    Only lowercase letters, numbers and hyphens are kept.
    Falls back to 'untitled' if nothing meaningful is left.
    """
    v = (value or "").strip().lower()
    v = re.sub(r"[^a-z0-9\s-]", "", v)
    v = re.sub(r"[\s]+", "-", v)
    v = re.sub(r"-+", "-", v)
    v = v.strip("-")
    if not v:
        v = "untitled"
    return v[:200]

def generate_unique_slug(db: Session, base: str, exclude_id: Optional[int] = None) -> str:
    """Generate a unique slug based on base. If a slug already exists, append a suffix.
    exclude_id is used during updates to allow the current row to keep its slug.
    """
    base_slug = slugify_value(base)
    candidate = base_slug
    counter = 1
    # Try incremental suffixes first (slug-1, slug-2, ...); fall back to uuid if necessary
    while True:
        existing = db.query(models.Post).filter(models.Post.slug == candidate).first()
        if not existing:
            return candidate
        if exclude_id and existing.id == exclude_id:
            return candidate
        candidate = f"{base_slug}-{counter}"
        counter += 1
        if counter > 20:
            candidate = f"{base_slug}-{uuid.uuid4().hex[:6]}"

# --- 文章 CRUD ---

def get_posts(db: Session, skip: int = 0, limit: int = 100, author_id: Optional[int] = None,
              search: Optional[str] = None, category: Optional[str] = None,
              tag: Optional[str] = None, include_hidden: bool = False):
    """获取文章列表,支持按作者筛选、搜索和分类过滤,包含作者信息"""
    # 使用 joinedload 预加载作者信息和标签,避免 N+1 查询问题
    query = db.query(models.Post).options(joinedload(models.Post.author), joinedload(models.Post.tags))

    if not include_hidden:
        query = query.filter(models.Post.is_hidden == False)

    if author_id:
        query = query.filter(models.Post.author_id == author_id)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (models.Post.title.like(search_filter)) |
            (models.Post.content.like(search_filter))
        )

    if category:
        query = query.filter(models.Post.category == category)

    if tag:
        query = query.join(models.Post.tags).filter(models.Tag.name == tag)

    # 按置顶优先级降序,然后按创建时间降序排序
    return query.order_by(models.Post.pin_priority.desc(), models.Post.created_at.desc()).offset(skip).limit(limit).all()

def get_post_by_id(db: Session, post_id: int):
    """根据 ID 获取文章,包含作者信息"""
    return db.query(models.Post).options(joinedload(models.Post.author), joinedload(models.Post.tags)).filter(models.Post.id == post_id).first()

def get_post_by_slug(db: Session, slug: str):
    """根据 Slug 获取文章"""
    return db.query(models.Post).options(joinedload(models.Post.author), joinedload(models.Post.tags)).filter(models.Post.slug == slug).first()

def create_post(db: Session, post: schemas.PostCreate, author_id: int):
    """创建文章"""
    try:
        # Ensure slug is present and unique
        incoming_slug = (getattr(post, 'slug', None) or "").strip()
        if incoming_slug:
            final_slug = generate_unique_slug(db, incoming_slug)
        else:
            final_slug = generate_unique_slug(db, post.title or "untitled")

        db_post = models.Post(
            title=post.title,
            content=post.content,
            category=post.category if hasattr(post, 'category') else "未分类",
            slug=final_slug,
            pin_priority=post.pin_priority,
            is_hidden=post.is_hidden,
            author_id=author_id
        )

        # 处理标签
        if post.tags:
            for tag_name in post.tags:
                if not tag_name or not isinstance(tag_name, str):
                    continue
                tag = get_tag_by_name(db, tag_name)
                if not tag:
                    tag = create_tag(db, tag_name)
                db_post.tags.append(tag)

        db.add(db_post)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            # Try to resolve slug conflict by regenerating a unique slug and retry once
            db_post.slug = generate_unique_slug(db, db_post.slug + '-' + uuid.uuid4().hex[:6])
            db.add(db_post)
            db.commit()
        db.refresh(db_post)
        return db_post
    except Exception as e:
        db.rollback()
        print(f"Error creating post: {e}")
        raise e

def update_post(db: Session, post_id: int, post_update: schemas.PostUpdate):
    """更新文章"""
    db_post = get_post_by_id(db, post_id)
    if not db_post:
        return None

    update_data = post_update.dict(exclude_unset=True)

    # 单独处理标签
    if "tags" in update_data:
        tags_data = update_data.pop("tags")
        db_post.tags = [] # 清空现有标签
        for tag_name in tags_data:
            tag = get_tag_by_name(db, tag_name)
            if not tag:
                tag = create_tag(db, tag_name)
            db_post.tags.append(tag)

    # Ensure slug stays valid/unique if provided
    if "slug" in update_data:
        incoming_slug = (update_data["slug"] or "").strip()
        if incoming_slug:
            update_data["slug"] = generate_unique_slug(db, incoming_slug, exclude_id=db_post.id)
        else:
            # If user cleared slug, regenerate from title (either new title or existing)
            title_source = update_data.get("title", db_post.title)
            update_data["slug"] = generate_unique_slug(db, title_source, exclude_id=db_post.id)

    for field, value in update_data.items():
        setattr(db_post, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # If slug caused conflict, regenerate using title and retry once
        if hasattr(db_post, 'slug'):
            db_post.slug = generate_unique_slug(db, (db_post.slug or db_post.title) + '-' + uuid.uuid4().hex[:6], exclude_id=db_post.id)
        db.add(db_post)
        db.commit()
    db.refresh(db_post)
    return db_post

def delete_post(db: Session, post_id: int):
    """删除文章"""
    db_post = get_post_by_id(db, post_id)
    if db_post:
        db.delete(db_post)
        db.commit()
        return True
    return False

def increment_post_views(db: Session, post_id: int):
    """增加文章浏览次数"""
    db_post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if db_post:
        db_post.views += 1
        db.commit()
        return True
    return False

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
