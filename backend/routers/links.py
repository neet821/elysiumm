from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

import crud, models, schemas
from database import get_db
from dependencies import get_current_user

router = APIRouter(
    tags=["links"],
    responses={404: {"description": "Not found"}},
)

# --- Category Endpoints ---

@router.get("/categories", response_model=List[schemas.LinkCategory])
def read_categories(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """获取当前用户的所有分类"""
    return crud.get_categories_by_user(db, current_user.id)

@router.post("/categories", response_model=schemas.LinkCategory)
def create_category(category: schemas.LinkCategoryCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """创建分类"""
    return crud.create_category(db, category, current_user.id)

@router.put("/categories/{category_id}", response_model=schemas.LinkCategory)
def update_category(category_id: int, category: schemas.LinkCategoryUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """更新分类"""
    db_category = crud.update_category(db, category_id, category, current_user.id)
    if db_category is None:
        raise HTTPException(status_code=404, detail="分类不存在或没有权限")
    return db_category

@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """删除分类"""
    success = crud.delete_category(db, category_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="分类不存在或没有权限")
    return {"status": "success"}

# --- Link Endpoints ---

@router.get("/links", response_model=List[schemas.WebsiteLink])
def read_links(category_id: Optional[int] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """获取链接(用户只能看到自己的 + 管理员的链接可能作为公共链接?
    目前CRUD逻辑是: get_links_by_user 返回 用户自己的 + 管理员的)
    """
    return crud.get_links_by_user(db, current_user.id, category_id)

@router.post("/links", response_model=schemas.WebsiteLink)
def create_link(link: schemas.WebsiteLinkCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """创建链接"""
    # 验证分类归属
    category = crud.get_category_by_id(db, link.category_id, current_user.id)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")

    return crud.create_link(db, link, current_user.id)

@router.put("/links/{link_id}", response_model=schemas.WebsiteLink)
def update_link(link_id: int, link: schemas.WebsiteLinkUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """更新链接"""
    db_link = crud.update_link(db, link_id, link, current_user.id)
    if db_link is None:
        raise HTTPException(status_code=404, detail="链接不存在或没有权限")
    return db_link

@router.delete("/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """删除链接"""
    success = crud.delete_link(db, link_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="链接不存在或没有权限")
    return {"status": "success"}
