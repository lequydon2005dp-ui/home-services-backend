from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float
from sqlalchemy.sql import func
from shared.database import Base
import enum

class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    WORKER = "worker"
    ADMIN = "admin"
    
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True) # Sửa thành True (không bắt buộc)
    avatar_url = Column(String(500), nullable=True) 
    role = Column(String(20), default=UserRole.CUSTOMER.value)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    rating = Column(Float, default=0.0) # Đánh giá sao thường là số thập phân
    total_reviews = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
class OTP(Base):
    __tablename__ = "otps"
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), index=True, nullable=False)
    otp = Column(String(6), nullable=False) # Sửa opt -> otp
    expires_at = Column(DateTime(timezone=True), nullable=False) # Sửa expiress_at
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())