"""User link and link-category persistence operations."""

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
import schemas


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
