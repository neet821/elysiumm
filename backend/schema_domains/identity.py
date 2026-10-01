from __future__ import annotations


from schema_domains._base import BaseModel, EmailStr, List, Optional, datetime, field_validator, validate_new_password, validate_username
from schema_domains.content import Post

class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str

    @field_validator("username")
    @classmethod
    def validate_new_username(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("password")
    @classmethod
    def validate_registration_password(cls, value: str) -> str:
        return validate_new_password(value)


class UserUpdate(BaseModel):
    """用户信息更新"""
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("password")
    @classmethod
    def validate_optional_password(cls, value: Optional[str]) -> Optional[str]:
        return validate_new_password(value) if value is not None else None


class UserPasswordUpdate(BaseModel):
    """密码修改"""
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_replacement_password(cls, value: str) -> str:
        return validate_new_password(value)


class UserUsernameUpdate(BaseModel):
    """用户名修改"""
    new_username: str

    @field_validator("new_username")
    @classmethod
    def validate_replacement_username(cls, value: str) -> str:
        return validate_username(value)


class User(UserBase):
    id: int
    avatar: Optional[str] = None  # 🆕 头像URL
    role: str = "user"
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None
    posts: List[Post] = []

    class Config:
        from_attributes = True


class UserSimple(UserBase):
    """简化的用户信息(用于列表显示)"""
    id: int
    avatar: Optional[str] = None  # 🆕 头像URL
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    user: Optional[UserSimple] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenData(BaseModel):
    username: Optional[str] = None
