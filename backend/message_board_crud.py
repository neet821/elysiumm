"""Message-board persistence operations."""

from sqlalchemy.orm import Session, joinedload

import models
import schemas


def create_message_board_entry(db: Session, message: schemas.MessageBoardCreate, user_id: int):
    db_message = models.MessageBoard(
        content=message.content,
        user_id=user_id,
        parent_id=message.parent_id
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message


def get_message_board_entries(db: Session, skip: int = 0, limit: int = 100):
    return (
        db.query(models.MessageBoard)
        .filter(models.MessageBoard.parent_id == None)  # noqa: E711
        .options(joinedload(models.MessageBoard.user), joinedload(models.MessageBoard.replies).joinedload(models.MessageBoard.user))
        .order_by(models.MessageBoard.created_at.desc())
        .offset(skip).limit(limit).all()
    )


def like_message(db: Session, message_id: int, user_id: int):
    # 检查是否已经点赞
    existing_like = db.query(models.MessageLike).filter(
        models.MessageLike.message_id == message_id,
        models.MessageLike.user_id == user_id
    ).first()

    if existing_like:
        # 如果已点赞，则取消点赞
        db.delete(existing_like)
        message = db.query(models.MessageBoard).filter(models.MessageBoard.id == message_id).first()
        if message:
            message.likes = max(0, message.likes - 1)
            db.commit()
            db.refresh(message)
            return message
    else:
        # 如果未点赞，则添加点赞
        new_like = models.MessageLike(message_id=message_id, user_id=user_id)
        db.add(new_like)
        message = db.query(models.MessageBoard).filter(models.MessageBoard.id == message_id).first()
        if message:
            message.likes += 1
            db.commit()
            db.refresh(message)
            return message

    return None


def delete_message(db: Session, message_id: int, user_id: int, is_admin: bool = False):
    """删除留言板消息，允许管理员或作者删除，并清理关联的点赞/子回复"""
    message = db.query(models.MessageBoard).filter(models.MessageBoard.id == message_id).first()
    if not message:
        return False, "留言不存在"

    if (not is_admin) and message.user_id != user_id:
        return False, "Permission denied"

    try:
        # 删除该消息及其子回复的点赞
        message_ids = [message.id]
        child_ids = [m.id for m in message.replies]
        message_ids.extend(child_ids)
        if message_ids:
            db.query(models.MessageLike).filter(models.MessageLike.message_id.in_(message_ids)).delete(synchronize_session=False)

        # 删除子回复
        for child in message.replies:
            db.delete(child)

        # 删除主消息
        db.delete(message)
        db.commit()
        return True, "Message deleted"
    except Exception as e:
        db.rollback()
        print(f"删除留言失败: {e}")
        return False, "Delete failed"
