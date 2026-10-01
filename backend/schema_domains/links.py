from __future__ import annotations


from schema_domains._base import BaseModel, List, Optional, datetime

class LinkCategoryBase(BaseModel):
    name: str
    description: Optional[str] = None


class LinkCategoryCreate(LinkCategoryBase):
    pass


class LinkCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class LinkCategory(LinkCategoryBase):
    id: int
    user_id: int
    created_at: datetime
    links: List['WebsiteLink'] = []

    class Config:
        from_attributes = True


class WebsiteLinkBase(BaseModel):
    title: str
    url: str
    description: Optional[str] = None
    category_id: int


class WebsiteLinkCreate(WebsiteLinkBase):
    pass


class WebsiteLinkUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None


class WebsiteLink(WebsiteLinkBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
