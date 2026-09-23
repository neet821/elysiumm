"""Accounts database models."""

from .base import (
    Base,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    datetime,
    relationship,
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    avatar = Column(String(500), nullable=True)  # 🆕 头像URL
    role = Column(String(20), default="user", nullable=False)  # 'admin' 或 'user'
    is_active = Column(Boolean, default=True, nullable=False)  # 账号是否启用
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    posts = relationship("Post", back_populates="author")
