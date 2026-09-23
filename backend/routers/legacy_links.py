"""HTTP handlers for legacy links."""

from fastapi import Depends, HTTPException, status

from sqlalchemy.orm import Session

import logging

import crud, models, schemas

from database import get_db

from dependencies import get_current_user

from fastapi import APIRouter

logger = logging.getLogger("backend")

router = APIRouter()


@router.get("/api/categories")
def get_categories(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """获取当前用户的所有分类"""
    return crud.get_categories_by_user(db, user_id=current_user.id)


@router.post("/api/categories", status_code=status.HTTP_201_CREATED)
def create_category(
    category: schemas.LinkCategoryCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建分类"""
    return crud.create_category(db, category, user_id=current_user.id)


@router.put("/api/categories/{category_id}")
def update_category(
    category_id: int,
    category_update: schemas.LinkCategoryUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新分类"""
    db_category = crud.update_category(
        db, category_id, category_update, user_id=current_user.id
    )
    if not db_category:
        raise HTTPException(status_code=404, detail="分类不存在")
    return db_category


@router.delete("/api/categories/{category_id}")
def delete_category(
    category_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除分类"""
    success = crud.delete_category(db, category_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="分类不存在")
    return {"message": "分类已删除"}


@router.get("/api/links")
def get_links(
    category_id: int = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的链接，可按分类筛选"""
    return crud.get_links_by_user(db, user_id=current_user.id, category_id=category_id)


@router.post("/api/links", status_code=status.HTTP_201_CREATED)
def create_link(
    link: schemas.WebsiteLinkCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建链接"""
    # 验证分类是否属于当前用户
    category = crud.get_category_by_id(db, link.category_id, user_id=current_user.id)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")

    return crud.create_link(db, link, user_id=current_user.id)


@router.put("/api/links/{link_id}")
def update_link(
    link_id: int,
    link_update: schemas.WebsiteLinkUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新链接"""
    # 如果要修改分类,验证分类是否属于当前用户
    if link_update.category_id:
        category = crud.get_category_by_id(
            db, link_update.category_id, user_id=current_user.id
        )
        if not category:
            raise HTTPException(status_code=404, detail="分类不存在")

    db_link = crud.update_link(db, link_id, link_update, user_id=current_user.id)
    if not db_link:
        raise HTTPException(status_code=404, detail="链接不存在")
    return db_link


@router.delete("/api/links/{link_id}")
def delete_link(
    link_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除链接"""
    success = crud.delete_link(db, link_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="链接不存在")
    return {"message": "链接已删除"}
