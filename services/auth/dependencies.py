from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt
import os

from shared.database import get_db
import crud, schemas

security = HTTPBearer()
SECRET_KEY = os.getenv("SECRET_KEY", "home-services-super-secret-key")
ALGORITHM = "HS256"

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        phone: str = payload.get("sub")
        if phone is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token đã hết hạn hoặc sai")
        
    user = crud.get_user_by_phone(db, phone=phone)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy User")
    return user