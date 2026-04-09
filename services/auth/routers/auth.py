from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import schemas, crud
from ...database import get_db

router = APIRouter()

@router.post("/register", response_model=schemas.UserResponse, status_code=201)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_phone(db, user.phone)
    if db_user:
        raise HTTPException(status_code=400, detail="Phone already registered")
    return crud.create_user(db, user)

@router.post("/login", response_model=schemas.Token)
def login(form_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, form_data.phone, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone or password"
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@router.post("/otp/send")
def send_otp(phone: str, db: Session = Depends(get_db)):
    otp = crud.create_otp(db, phone)
    # TODO: Send SMS via Twilio/Vonage
    print(f"OTP for {phone}: {otp}")  # Demo
    return {"message": "OTP sent successfully"}

@router.post("/otp/verify")
def verify_otp(phone: str, otp: str, db: Session = Depends(get_db)):
    if crud.verify_otp(db, phone, otp):
        return {"message": "OTP verified successfully"}
    raise HTTPException(status_code=400, detail="Invalid or expired OTP")