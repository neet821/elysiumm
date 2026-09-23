"""Content database models."""

from .base import (
    Base,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    datetime,
    relationship,
)


post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)


photo_tags = Table(
    "photo_tags",
    Base.metadata,
    Column("photo_id", Integer, ForeignKey("photos.id")),
    Column("tag_id", Integer, ForeignKey("tags.id")),
)


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    category = Column(String(50), nullable=True, default="未分类")
    views = Column(Integer, default=0)  # 浏览次数
    slug = Column(String(200), unique=True, index=True, nullable=True)  # 🆕 URL Slug
    pin_priority = Column(Integer, default=0)  # 🆕 置顶优先级 (0=无, 1=低, 2=中, 3=高)
    is_hidden = Column(Boolean, default=False)  # 🆕 是否隐藏
    author_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    author = relationship("User", back_populates="posts")
    tags = relationship("Tag", secondary=post_tags, back_populates="posts")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    color = Column(String(20), default="blue")  # 标签颜色
    created_at = Column(DateTime, default=datetime.utcnow)

    posts = relationship("Post", secondary=post_tags, back_populates="tags")
    photos = relationship("Photo", secondary=photo_tags, back_populates="tags")


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(500), nullable=False)
    caption = Column(String(200), nullable=True)  # 注释
    location = Column(String(100), nullable=True)  # 地点
    is_featured = Column(Boolean, default=False)  # 是否在首页展示
    created_at = Column(DateTime, default=datetime.utcnow)

    tags = relationship("Tag", secondary=photo_tags, back_populates="photos")
