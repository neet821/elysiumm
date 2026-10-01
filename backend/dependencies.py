from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import security
import crud
import models


def get_current_user(
    token: str = Depends(security.oauth2_scheme), db: Session = Depends(get_db)
):
    """从 token 获取当前用户"""
    username = security.decode_access_token(token)
    user = crud.get_user_by_username(db, username=username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已停用",
        )
    return user


def get_current_admin(current_user: models.User = Depends(get_current_user)):
    """所有管理员接口共享同一认证和权限依赖。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限"
        )
    return current_user
