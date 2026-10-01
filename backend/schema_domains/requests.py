from __future__ import annotations


from schema_domains._base import BaseModel, List, Optional, datetime
from schema_domains.identity import UserSimple

class ResourceRequestBase(BaseModel):
    title: str
    content: str
    is_anonymous: bool = False
    is_private: bool = False


class ResourceRequestCreate(ResourceRequestBase):
    pass


class WishlistReplyBase(BaseModel):
    content: str


class WishlistReplyCreate(WishlistReplyBase):
    pass


class WishlistReply(WishlistReplyBase):
    id: int
    request_id: int
    user_id: int
    created_at: datetime
    user: Optional[UserSimple] = None

    class Config:
        from_attributes = True


class ResourceRequestUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    reply_content: Optional[str] = None
    file_url: Optional[str] = None
    external_link: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_anonymous: Optional[bool] = None
    is_private: Optional[bool] = None


class ResourceRequest(ResourceRequestBase):
    id: int
    user_id: int
    status: str
    reply_content: Optional[str] = None
    file_url: Optional[str] = None
    external_link: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    user: Optional[UserSimple] = None
    replies: List[WishlistReply] = []

    class Config:
        from_attributes = True
