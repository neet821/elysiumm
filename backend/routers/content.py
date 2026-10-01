"""HTTP handlers for tags, posts, and the message board."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import crud
import models
import schemas
from database import get_db
from dependencies import get_current_admin, get_current_user
from routers import photo_routes

router = APIRouter()


@router.get("/api/tags", response_model=list[schemas.Tag])
def read_tags(db: Session = Depends(get_db)):
    return crud.get_all_tags(db)


@router.post("/api/tags", response_model=schemas.Tag)
def create_tag(
    tag: schemas.TagCreate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return crud.create_tag(db, tag.name, tag.color)


@router.get("/api/posts", response_model=list[schemas.PostWithAuthor])
def read_posts(
    skip: int = 0,
    limit: int = 100,
    author_id: int = None,
    search: str = None,
    category: str = None,
    tag: str = None,
    include_hidden: bool = False,
    db: Session = Depends(get_db),
):
    """获取文章列表,支持分页、按作者筛选、搜索和分类过滤"""
    try:
        # 限制最大返回数量,避免一次性查询过多数据
        limit = min(limit, 100)
        posts = crud.get_posts(
            db,
            skip=skip,
            limit=limit,
            author_id=author_id,
            search=search,
            category=category,
            tag=tag,
            include_hidden=include_hidden,
        )
        return posts
    except Exception as e:
        # 记录错误但返回空列表,避免前端崩溃
        print(f"Error fetching posts: {e}")
        return []


@router.get("/api/posts/{id_or_slug}", response_model=schemas.PostWithAuthor)
def read_post(id_or_slug: str, db: Session = Depends(get_db)):
    """获取单篇文章详情并增加浏览次数"""
    if id_or_slug.isdigit():
        post = crud.get_post_by_id(db, int(id_or_slug))
    else:
        post = crud.get_post_by_slug(db, id_or_slug)

    if not post:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 增加浏览次数
    crud.increment_post_views(db, post.id)

    # 重新获取更新后的文章（包含新的浏览次数）
    return crud.get_post_by_id(db, post.id)


@router.post(
    "/api/posts", response_model=schemas.Post, status_code=status.HTTP_201_CREATED
)
def create_post(
    post: schemas.PostCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建文章（仅管理员）"""
    # 权限检查：仅管理员可以创建文章
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以创建文章")

    return crud.create_post(db, post, author_id=current_user.id)


@router.put("/api/posts/{post_id}", response_model=schemas.Post)
def update_post(
    post_id: int,
    post_update: schemas.PostUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新文章（仅作者或管理员）"""
    db_post = crud.get_post_by_id(db, post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 权限检查：仅作者或管理员可以编辑
    if db_post.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="没有权限编辑这篇文章")

    updated_post = crud.update_post(db, post_id, post_update)
    return updated_post


@router.delete("/api/posts/{post_id}")
def delete_post(
    post_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除文章（仅作者或管理员）"""
    db_post = crud.get_post_by_id(db, post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 权限检查：仅作者或管理员可以删除
    if db_post.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="没有权限删除这篇文章")

    crud.delete_post(db, post_id)
    return {"message": "文章已删除"}


get_photos = photo_routes.get_photos
upload_photo_file = photo_routes.upload_photo_file
create_photo = photo_routes.create_photo
get_photo = photo_routes.get_photo
update_photo = photo_routes.update_photo
delete_photo = photo_routes.delete_photo

router.include_router(photo_routes.router)


@router.get("/api/messages", response_model=list[schemas.MessageBoardResponse])
def read_messages(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_message_board_entries(db, skip=skip, limit=limit)


@router.post(
    "/api/messages",
    response_model=schemas.MessageBoardResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    message: schemas.MessageBoardCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.create_message_board_entry(db, message, user_id=current_user.id)


@router.post(
    "/api/messages/{message_id}/like", response_model=schemas.MessageBoardResponse
)
def like_message(
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = crud.like_message(db, message_id, user_id=current_user.id)
    if not message:
        raise HTTPException(status_code=404, detail="留言不存在")
    return message


@router.delete("/api/messages/{message_id}")
def delete_message(
    message_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除留言（作者或管理员）"""
    success, reason = crud.delete_message(
        db, message_id, user_id=current_user.id, is_admin=current_user.role == "admin"
    )
    if not success:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if reason == "留言不存在"
            else status.HTTP_403_FORBIDDEN
        )
        raise HTTPException(status_code=status_code, detail=reason)
    return {"message": reason}
