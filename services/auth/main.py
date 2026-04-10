from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt
import os
import httpx
import base64
from twilio.rest import Client
import asyncio


from shared.database import engine, get_db
import models, schemas, crud

# Khởi tạo DB
models.Base.metadata.create_all(bind=engine)

loop = asyncio.get_event_loop()

SECRET_KEY = os.getenv("SECRET_KEY", "home-services-super-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")

twilio_client = Client(account_sid, auth_token) if account_sid and auth_token else None

app = FastAPI(title="Auth Service API", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def format_phone(phone: str):
    if phone.startswith("0"):
        return "+84" + phone[1:]
    if phone.startswith("84"):
        return "+" + phone
    return phone

@app.post("/auth/register", response_model=schemas.UserResponse, tags=["auth"])
async def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_phone(db, phone=user.phone):
        raise HTTPException(status_code=400, detail="SĐT đã được đăng ký")
    return crud.create_user(db=db, user=user)

@app.post("/auth/login/password", tags=["auth"])
async def login_password(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = crud.authenticate_user(db, phone=user.phone, password=user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="SĐT hoặc Mật khẩu không đúng")
    
    token = create_access_token(data={"sub": db_user.phone, "role": db_user.role, "id": db_user.id})
    return {"access_token": token, "token_type": "bearer", "role": db_user.role}

@app.post("/auth/otp/send", tags=["auth"])
async def send_otp(request: schemas.OTPRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_phone(db, request.phone)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản với SĐT này")
    
    otp_code = crud.create_otp(db, request.phone)

    print("============== DEV MODE ==============")
    print(f"Mã OTP cho SĐT {request.phone} là: {otp_code}")
    print("======================================")

    # 🔥 TWILIO CONFIG
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone = os.getenv("TWILIO_PHONE")

    # fallback nếu thiếu env
    if not account_sid or not auth_token or not twilio_phone:
        print("❌ Missing Twilio env vars!")
        return {"message": f"OTP test: {otp_code}"}


    try:
        print(f"📱 Sending SMS to {request.phone} via Twilio")

        message = await loop.run_in_executor(
            None,
            lambda: twilio_client.messages.create(
                body=f"Home Services - Ma OTP cua ban la: {otp_code}. Co hieu luc 5 phut.",
                from_=twilio_phone,
                to=format_phone(request.phone)
            )
        )

        print(f"✅ SMS sent! SID: {message.sid}")

        return {"message": "Mã OTP đã gửi qua SMS"}

    except Exception as e:
        print(f"❌ Twilio Error: {repr(e)}")
        return {"message": f"Dev OTP: {otp_code} (SMS failed)"}

@app.post("/auth/login/otp", tags=["auth"])
async def login_otp(request: schemas.OTPVerify, db: Session = Depends(get_db)):
    is_valid = crud.verify_otp(db, request.phone, request.otp)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Mã OTP không hợp lệ hoặc đã hết hạn")
    
    # Đăng nhập thành công -> Cập nhật trạng thái đã xác thực và cấp token
    db_user = crud.get_user_by_phone(db, request.phone)
    db_user.is_verified = True
    db.commit()
    
    token = create_access_token(data={"sub": db_user.phone, "role": db_user.role, "id": db_user.id})
    return {"access_token": token, "token_type": "bearer", "role": db_user.role}