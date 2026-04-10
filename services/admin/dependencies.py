from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os

security = HTTPBearer()
# BẮT BUỘC: Secret Key này phải GIỐNG HỆT với key bên Auth Service
SECRET_KEY = os.getenv("SECRET_KEY", "home-services-super-secret-key")
ALGORITHM = "HS256"

# Hàm 1: Giải mã và lấy thông tin ngay từ Token (Không chọc DB)
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Giải mã token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        phone: str = payload.get("sub")
        role: str = payload.get("role")
        user_id: int = payload.get("id")
        
        if phone is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")
            
        # Trả về thẳng một Dictionary chứa thông tin user lấy từ Token
        return {
            "phone": phone,
            "role": role,
            "id": user_id
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token đã hết hạn. Vui lòng đăng nhập lại.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sai hoặc đã bị chỉnh sửa.")

# Hàm 2: Phân quyền (Ví dụ: Chỉ Admin mới được vào)
def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Quyền truy cập bị từ chối. Cần quyền Admin.")
    return current_user

# Hàm 3: Phân quyền (Ví dụ: Chỉ Thợ mới được nhận đơn)
def require_worker(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "worker":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ thợ mới được thao tác.")
    return current_user