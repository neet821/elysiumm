from __future__ import annotations


from schema_domains._base import BaseModel, Field, List, Optional, datetime

class MessageBoardBase(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    parent_id: Optional[int] = Field(default=None, gt=0)


class MessageBoardCreate(MessageBoardBase):
    pass


class MessageBoardResponse(MessageBoardBase):
    id: int
    user_id: int
    likes: int = 0
    created_at: datetime
    user: Optional['UserSimple'] = None  # noqa: F821 - rebuilt by schemas.py facade
    replies: List['MessageBoardResponse'] = []

    class Config:
        from_attributes = True
