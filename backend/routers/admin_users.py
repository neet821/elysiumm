"""HTTP handlers for admin users."""

from fastapi import Depends, HTTPException

from sqlalchemy.orm import Session

import os

import logging

import crud, models, schemas

from admin_audit import add_admin_audit

from api_rate_limit import enforce_user_rate_limit

from database import get_db

from fastapi import APIRouter

from dependencies import get_current_admin

logger = logging.getLogger("backend")

router = APIRouter()

ADMIN_USER_MUTATION_RATE_LIMIT_MAX = int(
    os.getenv("ADMIN_USER_MUTATION_RATE_LIMIT_MAX", "10")
)

ADMIN_USER_MUTATION_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("ADMIN_USER_MUTATION_RATE_LIMIT_WINDOW_SECONDS", "60")
)


@router.get("/api/admin/users", response_model=list[schemas.UserSimple])
def get_all_users(
    skip: int = 0,
    limit: int = 100,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """获取所有用户列表(仅管理员)"""
    return crud.get_all_users(db, skip=skip, limit=limit)


@router.get("/api/admin/users/{user_id}", response_model=schemas.User)
def get_user_detail(
    user_id: int,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """获取用户详细信息(仅管理员)"""
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.put("/api/admin/users/{user_id}", response_model=schemas.User)
def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """更新用户信息(仅管理员)"""
    enforce_user_rate_limit(
        db,
        actor_id=current_admin.id,
        action="admin_user_update",
        limit=ADMIN_USER_MUTATION_RATE_LIMIT_MAX,
        window_seconds=ADMIN_USER_MUTATION_RATE_LIMIT_WINDOW_SECONDS,
        resource_type="user",
        resource_id=user_id,
    )
    # 防止管理员修改自己的角色
    if user_id == current_admin.id and user_update.role:
        add_admin_audit(
            db,
            actor_id=current_admin.id,
            action="admin_user_update",
            resource_type="user",
            resource_id=user_id,
            outcome="failed",
            detail="reason=self_role_change",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="不能修改自己的角色")

    user = crud.update_user(db, user_id, user_update)
    if not user:
        add_admin_audit(
            db,
            actor_id=current_admin.id,
            action="admin_user_update",
            resource_type="user",
            resource_id=user_id,
            outcome="failed",
            detail="reason=not_found",
        )
        db.commit()
        raise HTTPException(status_code=404, detail="用户不存在")
    fields = ",".join(sorted(user_update.model_dump(exclude_none=True)))
    add_admin_audit(
        db,
        actor_id=current_admin.id,
        action="admin_user_update",
        resource_type="user",
        resource_id=user_id,
        detail=f"fields={fields}",
    )
    db.commit()
    return user


@router.delete("/api/admin/users/{user_id}")
def delete_user(
    user_id: int,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """删除用户(仅管理员)"""
    enforce_user_rate_limit(
        db,
        actor_id=current_admin.id,
        action="admin_user_delete",
        limit=ADMIN_USER_MUTATION_RATE_LIMIT_MAX,
        window_seconds=ADMIN_USER_MUTATION_RATE_LIMIT_WINDOW_SECONDS,
        resource_type="user",
        resource_id=user_id,
    )
    # 防止管理员删除自己
    if user_id == current_admin.id:
        add_admin_audit(
            db,
            actor_id=current_admin.id,
            action="admin_user_delete",
            resource_type="user",
            resource_id=user_id,
            outcome="failed",
            detail="reason=self_delete",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="不能删除自己的账户")

    success = crud.delete_user(db, user_id)
    if not success:
        add_admin_audit(
            db,
            actor_id=current_admin.id,
            action="admin_user_delete",
            resource_type="user",
            resource_id=user_id,
            outcome="failed",
            detail="reason=not_found",
        )
        db.commit()
        raise HTTPException(status_code=404, detail="用户不存在")
    add_admin_audit(
        db,
        actor_id=current_admin.id,
        action="admin_user_delete",
        resource_type="user",
        resource_id=user_id,
    )
    db.commit()
    return {"message": "用户已删除"}
