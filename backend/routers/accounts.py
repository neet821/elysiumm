"""HTTP handlers for accounts."""

from fastapi import Depends, HTTPException, UploadFile, File

from sqlalchemy.orm import Session

from datetime import timedelta

import shutil

from pathlib import Path

import uuid

import logging

import crud, models, schemas, security

from database import get_db

from dependencies import get_current_user

from config import config

from fastapi import APIRouter

logger = logging.getLogger("backend")

router = APIRouter()


@router.post("/api/users/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="用户名已被注册")
    db_user_email = crud.get_user_by_email(db, email=user.email)
    if db_user_email:
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    return crud.create_user(db=db, user=user)


@router.get("/api/users/me", response_model=schemas.User)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    """获取当前登录用户的信息"""
    return current_user


@router.put("/api/users/me/password")
def update_my_password(
    password_update: schemas.UserPasswordUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改当前用户密码"""
    result = crud.update_user_password(
        db, current_user.id, password_update.old_password, password_update.new_password
    )
    if result is False:
        raise HTTPException(status_code=400, detail="原密码不正确")
    if result is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"message": "密码已更新"}


@router.put("/api/users/me/username")
def update_my_username(
    payload: schemas.UserUsernameUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改当前用户用户名（需唯一）"""
    new_username = payload.new_username
    if new_username == current_user.username:
        return {"message": "用户名未变化"}
    # 检查重复
    exists = crud.get_user_by_username(db, username=new_username)
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    # 更新
    current_user.username = new_username
    db.commit()
    db.refresh(current_user)

    # 生成新 Token
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={
            "sub": current_user.username,
            "role": current_user.role,
            "user_id": current_user.id,
        },
        expires_delta=access_token_expires,
    )

    return {
        "message": "用户名修改成功",
        "username": current_user.username,
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/api/users/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传用户头像"""
    # 验证文件类型
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in config.ALLOWED_AVATAR_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式。支持的格式: {', '.join(config.ALLOWED_AVATAR_EXTENSIONS)}",
        )

    # 验证文件大小
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > config.MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 ({config.MAX_AVATAR_SIZE / (1024 * 1024):.1f}MB)",
        )

    # 删除旧头像
    if current_user.avatar and current_user.avatar.startswith("/uploads/avatars/"):
        old_filename = current_user.avatar.split("/")[-1]
        old_file_path = config.AVATAR_UPLOAD_DIR / old_filename
        if old_file_path.exists():
            try:
                old_file_path.unlink()
                print(f"✅ 已删除旧头像: {old_filename}")
            except Exception as e:
                print(f"⚠️  删除旧头像失败: {e}")

    # 生成唯一文件名
    unique_filename = f"{current_user.id}_{uuid.uuid4()}{file_ext}"
    file_path = config.AVATAR_UPLOAD_DIR / unique_filename

    # 保存文件
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")

    # 更新数据库
    current_user.avatar = f"/uploads/avatars/{unique_filename}"
    db.commit()

    return {"message": "头像上传成功", "avatar_url": current_user.avatar}


@router.delete("/api/users/me/avatar")
def delete_avatar(
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """删除用户头像"""
    if not current_user.avatar:
        raise HTTPException(status_code=404, detail="未设置头像")

    # 删除文件
    if current_user.avatar.startswith("/uploads/avatars/"):
        filename = current_user.avatar.split("/")[-1]
        file_path = config.AVATAR_UPLOAD_DIR / filename
        if file_path.exists():
            try:
                file_path.unlink()
                print(f"✅ 已删除头像文件: {filename}")
            except Exception as e:
                print(f"⚠️  删除头像文件失败: {e}")

    # 更新数据库
    current_user.avatar = None
    db.commit()

    return {"message": "头像已删除"}
