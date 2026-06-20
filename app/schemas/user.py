from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from ..models.user import UserRole


class UserBase(BaseModel):
    username: str
    real_name: str
    email: Optional[str] = None
    role: UserRole = UserRole.CALL_AGENT
    store_id: Optional[int] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None
    store_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
