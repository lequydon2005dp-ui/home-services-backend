import asyncio
import time
import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, Float, DateTime, text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid
import httpx # 👉 Thêm thư viện này để gọi API nội bộ
import redis.asyncio as redis  # Thêm dòng này vào đầu file
import json

# Nên dùng biến môi trường, nhưng nếu Đôn đang test thì hardcode tạm cũng không sao!
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres:5432/home_services")
print(f"🔗 Using DATABASE_URL: {DATABASE_URL}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI(title="Order Service API v1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_uuid = Column(String(36), unique=True)
    customer_phone = Column(String(20))
    service_type = Column(String(50))
    address = Column(String(255))
    price = Column(Float)
    assigned_worker_id = Column(String(50), nullable=True)
    status = Column(String(20), default="pending")
    lat = Column(Float)
    lng = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

class AcceptJobRequest(BaseModel):
    worker_id: str
    
class OrderStatusUpdate(BaseModel):
    status: str      # Trạng thái muốn chuyển sang (in_progress, completed, cancelled)
    worker_id: str
    
# ✅ RETRY LOGIC của Đôn - Rất tốt!
async def wait_for_db(max_retries=30, delay=2):
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ Database connected successfully!")
            return True
        except Exception as e:
            print(f"⚠️  DB connection attempt {i+1}/{max_retries} failed: {e}")
            if i < max_retries - 1:
                time.sleep(delay)
    return False

@app.on_event("startup")
async def startup_event():
    print("🚀 Starting Order Service...")
    if await wait_for_db():
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully!")
    else:
        raise RuntimeError("❌ Cannot connect to database after retries")

class OrderCreate(BaseModel):
    customer_phone: str
    service_type: str
    address: str
    price: float
    lat: float # Bắt buộc có tọa độ để còn ghép thợ
    lng: float

# URL của Matching Service trong mạng Docker
MATCHING_SERVICE_URL = "http://matching-service:8000/matching/find"
redis_client = redis.Redis.from_url("redis://redis:6379", decode_responses=True)
@app.get("/health", tags=["health"])
async def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "🟢 HEALTHY", "database": "PostgreSQL ✅"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")

@app.post("/order/create", tags=["order"])
async def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    # 1. Lưu đơn hàng vào DB bằng logic của Đôn
    new_uuid = str(uuid.uuid4())
    db_order = Order(**order.model_dump(), order_uuid=new_uuid)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    notification = {
        "event": "NEW_ORDER",
        "order_uuid": new_uuid,
        "service_type": order.service_type,
        "address": order.address,
        "price": order.price,
        "message": "Bạn Có Đơn Hàng Mới!"
    }
    await redis_client.publish("broadcast:workers", json.dumps(notification))
    
    # 2. 👉 Tự động gọi sang Matching Service để tìm thợ
    matching_payload = {
        "order_uuid": new_uuid,
        "service_type": order.service_type,
        "lat": order.lat,
        "lng": order.lng
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Gọi API bất đồng bộ
            response = await client.post(MATCHING_SERVICE_URL, json=matching_payload)
            
            if response.status_code == 200:
                return {
                    "message": "✅ Đã tạo đơn và tìm thấy thợ!",
                    "order_id": db_order.id,
                    "matching_info": response.json()
                }
            else:
                return {
                    "message": "⚠️ Đã tạo đơn nhưng chưa tìm thấy thợ phù hợp ở gần.",
                    "order_id": db_order.id,
                    "detail": response.text
                }
    except Exception as e:
         return {
            "message": "⚠️ Đã tạo đơn nhưng lỗi kết nối hệ thống Matching.",
            "order_id": db_order.id,
            "error": str(e)
        }

@app.get("/order/list", tags=["order"])
async def list_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).limit(50).all()
    return orders

@app.put("/order/{order_uuid}/accept", tags=["order"])
async def accept_order(order_uuid: str, request: AcceptJobRequest, db: Session = Depends(get_db)):
    # 1. Tìm đơn hàng trong DB
    order = db.query(Order).filter(Order.order_uuid == order_uuid).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng này")

    # 2. Kiểm tra xem đơn có còn "trống" không (tránh trường hợp 2 thợ cùng bấm nhận)
    if order.status != "pending":
        raise HTTPException(
            status_code=400, 
            detail="Rất tiếc! Đơn hàng này đã có người khác nhận hoặc đã bị hủy."
        )

    # 3. Gán thợ vào đơn và cập nhật trạng thái
    order.status = "assigned"
    order.assigned_worker_id = request.worker_id
    db.commit()
    db.refresh(order)

    # 4. (Tính năng xịn sò) Bắn thông báo ngược lại cho Customer là "Đã có thợ nhận đơn"
    # Bạn có thể tích hợp gọi HTTP sang Notification Service ở đây sau này

    return {
        "message": f"🎉 Chúc mừng! Thợ {request.worker_id} đã nhận đơn thành công.",
        "order_uuid": order.order_uuid,
        "status": order.status
    }

@app.put("/order/{order_uuid}/status", tags=["order"])
async def update_order_status(order_uuid: str, request: OrderStatusUpdate, db: Session = Depends(get_db)):
    # 1. Tìm đơn hàng
    order = db.query(Order).filter(Order.order_uuid == order_uuid).first()
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng này")

    # 2. Bảo mật: Chỉ người thợ đã nhận đơn mới được phép cập nhật
    if request.worker_id != "SYSTEM" and order.assigned_worker_id != request.worker_id:
        raise HTTPException(status_code=403, detail="⚠️ Bạn không có quyền cập nhật đơn hàng của người khác!")

    # 3. Máy trạng thái (State Machine): Chặn việc nhảy cóc trạng thái
    valid_transitions = {
        "pending": ["assigned", "cancelled"],
        "assigned": ["in_progress", "cancelled"],     # Từ 'Đã nhận' chỉ có thể 'Đang làm' hoặc 'Hủy'
        "in_progress": ["completed", "cancelled"],
        "completed": ["paid"],
        "paid": []
        # Từ 'Đang làm' chỉ có thể 'Hoàn thành' hoặc 'Hủy'
    }

    # Nếu trạng thái hiện tại không có trong từ điển, hoặc trạng thái muốn chuyển tới không hợp lệ
    current_status = order.status
    if current_status not in valid_transitions or request.status not in valid_transitions[current_status]:
        raise HTTPException(
            status_code=400, 
            detail=f"❌ Thao tác không hợp lệ: Không thể chuyển trạng thái từ '{current_status}' sang '{request.status}'"
        )

    # 4. Lưu trạng thái mới
    order.status = request.status
    db.commit()

    # (Tính năng mở rộng): Nếu trạng thái là 'completed', lúc này có thể gọi sang Payment Service
    if request.status == "completed":
        print(f"💰 Đơn {order_uuid} đã xong, chuẩn bị kích hoạt thanh toán!")
        # await call_payment_service(...)

    return {
        "message": f"✅ Cập nhật thành công! Đơn hàng hiện đang ở trạng thái: {request.status}",
        "order_uuid": order_uuid
    }
    
@app.get("/order/{order_uuid}", tags=["order"])
async def get_order_details(order_uuid: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_uuid == order_uuid).first()
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    
    # Logic hiển thị thân thiện
    payment_status = "Đã thanh toán" if order.status == "paid" else "Chưa thanh toán"
    
    return {
        "order_uuid": order.order_uuid,
        "current_status": order.status,
        "price": order.price,
        "payment_info": payment_status,
        "worker_assigned": order.assigned_worker_id
    }