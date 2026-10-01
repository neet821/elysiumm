from __future__ import annotations


from schema_domains._base import BaseModel, List, Optional, datetime

class TagBase(BaseModel):
    name: str
    color: Optional[str] = "#3B82F6"


class TagCreate(TagBase):
    pass


class Tag(TagBase):
    id: int

    class Config:
        from_attributes = True


class PostBase(BaseModel):
    title: str
    content: Optional[str] = None
    category: Optional[str] = "未分类"  # 新增分类字段
    slug: Optional[str] = None
    pin_priority: int = 0
    is_hidden: bool = False


class PostCreate(PostBase):
    """创建文章的请求模型"""
    tags: List[str] = []


class PostUpdate(BaseModel):
    """更新文章的请求模型"""
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None  # 新增分类字段
    slug: Optional[str] = None
    pin_priority: Optional[int] = None
    is_hidden: Optional[bool] = None
    tags: Optional[List[str]] = None


class Post(PostBase):
    """文章响应模型"""
    id: int
    author_id: int
    views: int = 0  # 浏览次数
    created_at: datetime
    tags: List[Tag] = []

    class Config:
        from_attributes = True


class PostWithAuthor(Post):
    """带作者信息的文章模型"""
    author: Optional['UserSimple'] = None  # noqa: F821 - rebuilt by schemas.py facade

    class Config:
        from_attributes = True


class PhotoBase(BaseModel):
    url: str
    caption: Optional[str] = None
    location: Optional[str] = None
    is_featured: bool = False


class PhotoCreate(PhotoBase):
    tags: List[str] = []


class PhotoUpdate(BaseModel):
    url: Optional[str] = None
    caption: Optional[str] = None
    location: Optional[str] = None
    is_featured: Optional[bool] = None
    tags: Optional[List[str]] = None


class Photo(PhotoBase):
    id: int
    created_at: datetime
    tags: List[Tag] = []

    class Config:
        from_attributes = True
