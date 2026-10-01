"""Account persistence operations."""

from sqlalchemy.orm import Session

import models
import schemas
import security

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = security.get_password_hash(user.password)

    # 检查是否是第一个用户,如果是则设为管理员
    user_count = db.query(models.User).count()
    role = "admin" if user_count == 0 else "user"

    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_all_users(db: Session, skip: int = 0, limit: int = 100):
    """获取所有用户(管理员功能)"""
    return db.query(models.User).offset(skip).limit(limit).all()

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate):
    """更新用户信息(管理员功能)"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None

    update_data = user_update.dict(exclude_unset=True)

    # 如果要更新密码,需要加密
    if "password" in update_data:
        update_data["hashed_password"] = security.get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_password(db: Session, user_id: int, old_password: str, new_password: str):
    """用户修改自己的密码"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None

    # 验证旧密码
    if not security.verify_password(old_password, db_user.hashed_password):
        return False

    # 更新密码
    db_user.hashed_password = security.get_password_hash(new_password)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    """删除用户(管理员功能) - 级联删除所有关联数据"""
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return False

    try:
        # 1. 删除用户的文章
        db.query(models.Post).filter(models.Post.author_id == user_id).delete()

        # 2. 删除用户的链接
        db.query(models.WebsiteLink).filter(models.WebsiteLink.user_id == user_id).delete()

        # 3. 删除用户的链接分类（会级联删除该分类下的所有链接）
        db.query(models.LinkCategory).filter(models.LinkCategory.user_id == user_id).delete()

        # 4. 删除用户的同步房间消息
        user_rooms = db.query(models.SyncRoom).filter(models.SyncRoom.host_user_id == user_id).all()
        for room in user_rooms:
            db.query(models.SyncRoomMessage).filter(models.SyncRoomMessage.room_id == room.id).delete()
            db.query(models.SyncRoomMember).filter(models.SyncRoomMember.room_id == room.id).delete()

        # 5. 删除用户的同步房间
        db.query(models.SyncRoom).filter(models.SyncRoom.host_user_id == user_id).delete()

        # 6. 删除用户作为成员的房间关系
        db.query(models.SyncRoomMember).filter(models.SyncRoomMember.user_id == user_id).delete()

        # 7. 删除用户发送的房间消息
        db.query(models.SyncRoomMessage).filter(models.SyncRoomMessage.user_id == user_id).delete()

        # 8. 最后删除用户
        db.delete(db_user)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"删除用户失败: {str(e)}")
        return False
