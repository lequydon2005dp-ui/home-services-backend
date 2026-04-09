from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    phone: str = Field(..., pattern=r"^\+?[0-9]\d{9,15}$")
    full_name: str

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    email: Optional[EmailStr] = None
    role: Optional[str] = "customer"
    
class UserLogin(BaseModel):
    phone: str
    password: str

class OTPRequest(BaseModel):
    phone: str

class OTPVerify(BaseModel):
    phone: str
    otp: str
    
class TokenData(BaseModel):
    user_id: Optional[int] = None
    role: Optional[str] = None
    
class UserResponse(UserBase):
    id: int
    email: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool
    rating: float = 0.0
    total_reviews: int = 0
    created_at: datetime
    
    class Config:
        from_attributes = True