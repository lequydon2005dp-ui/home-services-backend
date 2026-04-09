from sqlalchemy.orm import Session
from passlib.context import CryptContext
import models, schemas
import random
import string
from datetime import datetime, timedelta, timezone

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_user_by_phone(db: Session, phone: str):
    return db.query(models.User).filter(models.User.phone == phone).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(
        phone=user.phone,
        password_hash=hashed_password,
        full_name=user.full_name,
        email=user.email,
        role=user.role if user.role else models.UserRole.CUSTOMER.value
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, phone: str, password: str):
    user = get_user_by_phone(db, phone)
    if not user:
        return False
    if not pwd_context.verify(password, user.password_hash):
        return False
    return user

def create_otp(db: Session, phone: str):
    otp = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5) # Sống 5 phút
    
    # Xóa OTP cũ để tránh spam
    db.query(models.OTP).filter(models.OTP.phone == phone).delete()
    
    db_otp = models.OTP(phone=phone, otp=otp, expires_at=expires_at)
    db.add(db_otp)
    db.commit()
    return otp

def verify_otp(db: Session, phone: str, otp: str) -> bool:
    db_otp = db.query(models.OTP).filter(
        models.OTP.phone == phone,
        models.OTP.otp == otp,
        models.OTP.is_used == False,
        models.OTP.expires_at > datetime.now(timezone.utc)
    ).first()
    
    if db_otp:
        db_otp.is_used = True
        db.commit()
        return True
    return False