"""HTTP handlers for resource requests."""

from fastapi import Depends, HTTPException, status

from sqlalchemy.orm import Session

import logging

import crud, models, schemas

from database import get_db

from dependencies import get_current_user

from fastapi import APIRouter

logger = logging.getLogger("backend")

router = APIRouter()


@router.get("/api/resource-requests", response_model=list[schemas.ResourceRequest])
def read_resource_requests(
    skip: int = 0, limit: int = 100, status: str = None, db: Session = Depends(get_db)
):
    return crud.get_resource_requests(db, skip=skip, limit=limit, status=status)


@router.post(
    "/api/resource-requests",
    response_model=schemas.ResourceRequest,
    status_code=status.HTTP_201_CREATED,
)
def create_resource_request(
    request: schemas.ResourceRequestCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.create_resource_request(db, request, user_id=current_user.id)


@router.put(
    "/api/resource-requests/{request_id}", response_model=schemas.ResourceRequest
)
def update_resource_request(
    request_id: int,
    request_update: schemas.ResourceRequestUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_request = (
        db.query(models.ResourceRequest)
        .filter(models.ResourceRequest.id == request_id)
        .first()
    )
    if not db_request:
        raise HTTPException(status_code=404, detail="请求不存在")

    if current_user.role != "admin":
        if db_request.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="没有操作权限")
        if db_request.status != "pending":
            raise HTTPException(status_code=400, detail="只能编辑待处理的请求")
        if (
            request_update.status
            or request_update.reply_content
            or request_update.file_url
        ):
            raise HTTPException(status_code=403, detail="只有管理员可以更新状态或回复")

    return crud.update_resource_request(db, request_id, request_update)


@router.delete("/api/resource-requests/{request_id}")
def delete_resource_request(
    request_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_request = (
        db.query(models.ResourceRequest)
        .filter(models.ResourceRequest.id == request_id)
        .first()
    )
    if not db_request:
        raise HTTPException(status_code=404, detail="请求不存在")

    if current_user.role != "admin" and db_request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有操作权限")

    crud.delete_resource_request(db, request_id)
    return {"message": "请求已删除"}


@router.post(
    "/api/resource-requests/{request_id}/replies", response_model=schemas.WishlistReply
)
def create_wishlist_reply(
    request_id: int,
    reply: schemas.WishlistReplyCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.create_wishlist_reply(db, reply, request_id, current_user.id)
