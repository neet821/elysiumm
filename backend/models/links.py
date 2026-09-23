"""Links database models."""

from .base import (
    Base,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    datetime,
    relationship,
)


class LinkCategory(Base):
    __tablename__ = "link_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    description = Column(String(200), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    links = relationship(
        "WebsiteLink", back_populates="category", cascade="all, delete-orphan"
    )


class WebsiteLink(Base):
    __tablename__ = "website_links"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    description = Column(String(300), nullable=True)
    category_id = Column(Integer, ForeignKey("link_categories.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("LinkCategory", back_populates="links")
    user = relationship("User")
