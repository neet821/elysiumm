"""Synchronization-room membership and chat message models."""

from .base import (
    Base,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    datetime,
    relationship,
)


class SyncRoomMember(Base):
    __tablename__ = "sync_room_members"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    nickname = Column(String(50), nullable=True)  # 房间内昵称
    is_verified = Column(Boolean, default=True)  # 是否通过哈希校验(模式二使用)
    is_online = Column(Boolean, default=True)  # 是否在线
    last_active_at = Column(DateTime, default=datetime.utcnow)  # 最后活跃时间
    joined_at = Column(DateTime, default=datetime.utcnow)

    room = relationship("SyncRoom", back_populates="members")
    user = relationship("User")


class SyncRoomMessage(Base):
    __tablename__ = "sync_room_messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("sync_rooms.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    is_private = Column(Boolean, default=False)  # 🔧 是否为私信
    target_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # 🔧 私信目标用户
    created_at = Column(DateTime, default=datetime.utcnow)

    room = relationship("SyncRoom", back_populates="messages")
    user = relationship("User", foreign_keys=[user_id])
    target_user = relationship(
        "User", foreign_keys=[target_user_id]
    )  # 🔧 私信目标用户关系
