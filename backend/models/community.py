"""Community database models."""

from .base import (
    Base,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    backref,
    datetime,
    relationship,
)


class MessageBoard(Base):
    __tablename__ = "message_board"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("message_board.id"), nullable=True)  # 🆕
    likes = Column(Integer, default=0)  # 🆕
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    replies = relationship(
        "MessageBoard", backref=backref("parent", remote_side=[id])
    )  # 🆕


class MessageLike(Base):
    __tablename__ = "message_likes"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("message_board.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ResourceRequest(Base):
    __tablename__ = "resource_requests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(
        String(20), default="pending"
    )  # pending, completed, invalid, abandoned
    is_anonymous = Column(Boolean, default=False)  # 🆕
    is_private = Column(Boolean, default=False)  # 🆕

    # Fulfillment details
    reply_content = Column(Text, nullable=True)  # Admin reply
    file_url = Column(String(500), nullable=True)  # Uploaded file URL
    external_link = Column(String(500), nullable=True)  # External link
    expires_at = Column(DateTime, nullable=True)  # File expiration

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    replies = relationship(
        "WishlistReply", back_populates="request", cascade="all, delete-orphan"
    )  # 🆕


class WishlistReply(Base):  # 🆕
    __tablename__ = "wishlist_replies"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    request_id = Column(Integer, ForeignKey("resource_requests.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    request = relationship("ResourceRequest", back_populates="replies")
    user = relationship("User")
