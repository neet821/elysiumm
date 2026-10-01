"""Tag and article persistence operations."""

import re
import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

import models
import schemas


# --- Tag CRUD ---
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


# --- Slug helpers ---
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


# --- Article CRUD ---
def get_posts(db: Session, skip: int = 0, limit: int = 100, author_id: Optional[int] = None,
              search: Optional[str] = None, category: Optional[str] = None,
              tag: Optional[str] = None, include_hidden: bool = False):
    """获取文章列表,支持按作者筛选、搜索和分类过滤,包含作者信息"""
    # 使用 joinedload 预加载作者信息和标签,避免 N+1 查询问题
    query = db.query(models.Post).options(joinedload(models.Post.author), joinedload(models.Post.tags))

    if not include_hidden:
        query = query.filter(models.Post.is_hidden == False)  # noqa: E712

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
        except IntegrityError as e:  # noqa: F841
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
