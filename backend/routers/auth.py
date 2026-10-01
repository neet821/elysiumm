"""HTTP handlers for auth."""

from fastapi import Depends, HTTPException, status, Request

from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy.orm import Session

from datetime import timedelta

import os

import logging

import crud, models, schemas, security

from database import get_db

from dependencies import get_current_user

from rate_limit import SlidingWindowRateLimiter

from fastapi import APIRouter

logger = logging.getLogger("backend")

router = APIRouter()

LOGIN_RATE_LIMIT_MAX = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "5"))

LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")
)

login_rate_limiter = SlidingWindowRateLimiter()


def create_auth_response(user: models.User) -> dict:
    """生成统一登录/刷新响应"""
    token_payload = {
        "sub": user.username,
        "role": user.role,
        "user_id": user.id,
    }
    access_token = security.create_access_token(
        data=token_payload,
        expires_delta=timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = security.create_refresh_token(data=token_payload)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }


@router.post("/api/auth/login", response_model=schemas.Token)
def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    # 支持用户名或邮箱登录
    login_id = form_data.username.strip()
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"{client_host}:{login_id.casefold()}"
    retry_after = login_rate_limiter.retry_after(
        rate_key,
        limit=LOGIN_RATE_LIMIT_MAX,
        window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    )
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )
    user = None
    if "@" in login_id:
        user = crud.get_user_by_email(db, email=login_id)
    else:
        user = crud.get_user_by_username(db, username=login_id)

    if (
        not user
        or not user.is_active
        or not security.verify_password(form_data.password, user.hashed_password)
    ):
        login_rate_limiter.check(
            rate_key,
            limit=LOGIN_RATE_LIMIT_MAX,
            window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名/邮箱或密码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_rate_limiter.clear(rate_key)
    return create_auth_response(user)


@router.get("/api/auth/me", response_model=schemas.User)
def read_current_auth_user(current_user: models.User = Depends(get_current_user)):
    """获取当前登录用户的信息"""
    return current_user


@router.post("/api/auth/refresh", response_model=schemas.Token)
def refresh_access_token(
    payload: schemas.RefreshTokenRequest, db: Session = Depends(get_db)
):
    """使用 refresh token 续期登录态"""
    username = security.decode_refresh_token(payload.refresh_token)
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
    return create_auth_response(user)


@router.post("/api/auth/logout")
def logout_current_user(current_user: models.User = Depends(get_current_user)):
    """退出登录；当前版本由前端清理本地令牌"""
    return {"message": "已退出登录"}
