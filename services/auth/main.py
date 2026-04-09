from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt
import os
import httpx
import base64

from shared.database import engine, get_db
import models, schemas, crud

# Khởi tạo DB
models.Base.metadata.create_all(bind=engine)

SECRET_KEY = os.getenv("SECRET_KEY", "home-services-super-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

app = FastAPI(title="Auth Service API", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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
    
    # 🔥 SPEEDSMS OTP 
    speedsms_token = os.getenv("SPEEDSMS_ACCESS_TOKEN")
    
    # Kiểm tra env vars trước
    if not speedsms_token:
        print("❌ Missing SPEEDSMS env vars!")
        return {"message": f"OTP test: {otp_code}"}  # Fallback cho dev
    
    try:
        print(f"📱 Sending SMS to {request.phone} via SpeedSMS")
        
        # HTTP Cơ bản Auth: token:x
        auth_str = f"{speedsms_token}:x"
        b64_auth = base64.b64encode(auth_str.encode('ascii')).decode('ascii')
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.speedsms.vn/index.php/sms/send",
                headers={
                    "Authorization": f"Basic {b64_auth}",
                    "Content-Type": "application/json"
                },
                json={
                    "to": [request.phone],
                    "content": f"Home Services - Ma OTP cua ban la: {otp_code}. Co hieu luc trong 5 phut.",
                    "sms_type": 4, 
                    "sender": "" 
                },
                timeout=10.0
            )
            
            res_data = response.json()
            if res_data.get("status") == "success":
                print(f"✅ SMS sent! SpeedSMS Res: {res_data}")
                return {"message": "Mã OTP đã gửi qua SMS"}
            else:
                print(f"❌ SpeedSMS Error Response: {res_data}")
                return {"message": f"Dev OTP: {otp_code} (SpeedSMS failed: {res_data.get('message')})"}
                
    except Exception as e:
        print(f"❌ SMS Error: {str(e)}")
        # VẪN TRẢ OTP CHO DEV (không break flow)
        return {"message": f"Dev OTP: {otp_code} (SMS failed: {str(e)[:50]})"}

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