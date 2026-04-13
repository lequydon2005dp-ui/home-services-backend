import sys
import os
sys.path.append('/app')  # Fix import path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, ARRAY, Float, DateTime, text, create_engine, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, EmailStr, Field
from fastapi import WebSocket, WebSocketDisconnect
from websocket_manager import manager # Import bộ quản lý vừa tạo
from typing import List, Optional
from datetime import datetime
import asyncio
import uuid
import redis.asyncio as redis
import json

# ✅ HARDCODE Docker URL
DATABASE_URL = "postgresql://postgres:password@postgres:5432/home_services"
print(f"🔗 Worker Using DATABASE_URL: {DATABASE_URL}")

redis_client = redis.Redis.from_url("redis://redis:6379", decode_responses=True)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI(title="Worker Service API v1.0", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class Worker(Base):
    __tablename__ = "workers"
    id = Column(Integer, primary_key=True, index=True)
    worker_uuid = Column(String(36), unique=True, index=True)
    worker_id = Column(String(50), unique=True)
    full_name = Column(String(100))
    phone = Column(String(20))
    email = Column(String(100))
    skills = Column(ARRAY(String))
    lat = Column(Float)
    lng = Column(Float)
    rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)
    is_approved = Column(Boolean, default=False)
    status = Column(String(20), default="available")
    created_at = Column(DateTime, default=datetime.utcnow)

# Pydantic Models
class WorkerCreate(BaseModel):
    worker_id: str
    full_name: str
    phone: str
    email: Optional[EmailStr] = None
    skills: List[str]
    lat: Optional[float] = None
    lng: Optional[float] = None

class WorkerResponse(BaseModel):
    id: int
    worker_uuid: str
    worker_id: str
    full_name: str
    phone: str
    skills: List[str]
    rating: float
    status: str

# --- Database Models ---
class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    order_uuid = Column(String(50), unique=True) # Mỗi đơn chỉ đánh giá 1 lần
    worker_id = Column(String(50), index=True)
    customer_phone = Column(String(20))
    rating = Column(Integer) # Điểm từ 1-5
    comment = Column(Text, nullable=True)

# Giả sử bảng Worker đã có cột `rating` (điểm TB) và `total_reviews` (tổng lượt đánh giá)
# Base.metadata.create_all(bind=engine) # ĐÃ CHUYỂN XUỐNG HÀM wait_for_db ĐỂ CHỐNG LỖI SẬP DB KHI KHỞI ĐỘNG
# --- Pydantic Schema ---
class ReviewCreate(BaseModel):
    order_uuid: str
    worker_id: str
    customer_phone: str
    rating: int = Field(..., ge=1, le=5) # Ràng buộc FR25: Chỉ được chấm 1-5 sao
    comment: str = None

# Retry DB connection
async def wait_for_db(max_retries=60, delay=1):
    print("🚀 Worker Service - Waiting for PostgreSQL...")
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ Worker Database ready!")
            Base.metadata.create_all(bind=engine)
            print("✅ Worker Tables created!")
            return True
        except Exception as e:
            print(f"⚠️  Worker DB attempt {i+1}/{max_retries}: {str(e)[:80]}")
            await asyncio.sleep(delay)
    print("❌ Worker DB timeout!")
    return False

async def redis_listener():
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("new_orders_channel")
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await manager.broadcast(data)
            
@app.on_event("startup")
async def startup_event():
    # Chạy đồng thời việc đợi DB và nghe Redis
    await wait_for_db()
    asyncio.create_task(redis_listener())

@app.get("/", tags=["home"])
async def root():
    return {
        "message": "👷‍♂️ Home Services Worker API v1.0", 
        "version": "1.0.0",
        "endpoints": ["/health", "/worker/register", "/worker/list"]
    }

@app.get("/health", tags=["health"])
async def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "🟢 HEALTHY",
            "timestamp": datetime.now().isoformat(),
            "database": "PostgreSQL ✅ Connected"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")

@app.post("/worker/register", response_model=WorkerResponse, tags=["worker"])
async def register_worker(worker: WorkerCreate, db: Session = Depends(get_db)):
    # Check duplicate
    existing = db.query(Worker).filter(Worker.worker_id == worker.worker_id).first()
    if existing:
        raise HTTPException(400, "Worker ID already exists")
    
    db_worker = Worker(
        worker_uuid=str(uuid.uuid4()),
        **worker.model_dump()
    )
    db.add(db_worker)
    db.commit()
    db.refresh(db_worker)
    return db_worker

@app.get("/worker/list", tags=["worker"])
async def list_workers(db: Session = Depends(get_db), limit: int = 50):
    workers = db.query(Worker).order_by(Worker.created_at.desc()).limit(limit).all()
    return [WorkerResponse(**w.__dict__) for w in workers]

@app.get("/worker/{worker_id}", tags=["worker"])
async def get_worker(worker_id: str, db: Session = Depends(get_db)):
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(404, "Worker not found")
    return WorkerResponse(**worker.__dict__)


@app.get("/admin/workers/pending", tags=["Admin"])
async def get_pending_workers(db: Session = Depends(get_db)):
    # Lấy các thợ chưa được duyệt
    workers = db.query(Worker).filter(Worker.is_approved == False).all()
    return workers

# --- API 2: Nút bấm Duyệt thợ ---
@app.put("/admin/workers/{worker_id}/approve", tags=["Admin"])
async def approve_worker(worker_id: str, db: Session = Depends(get_db)):
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Không tìm thấy thợ này")
    
    # Chuyển trạng thái sang Đã duyệt
    worker.is_approved = True
    db.commit()
    
    return {"message": f"✅ Đã phê duyệt thành công cho thợ: {worker.full_name}"}
    
@app.post("/reviews/", tags=["Review & Rating"])
async def create_review(review: ReviewCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra xem đơn hàng này đã được đánh giá chưa
    existing_review = db.query(Review).filter(Review.order_uuid == review.order_uuid).first()
    if existing_review:
        raise HTTPException(status_code=400, detail="Đơn hàng này đã được đánh giá!")

    # 2. Lưu đánh giá vào Database
    db_review = Review(**review.model_dump())
    db.add(db_review)

    # 3. Tính toán lại Rating trung bình cho Worker (FR26)
    worker = db.query(Worker).filter(Worker.worker_id == review.worker_id).first()
    if worker:
        # Công thức cập nhật điểm trung bình chuẩn
        current_total = worker.total_reviews if worker.total_reviews else 0
        current_rating = worker.rating if worker.rating else 0.0
        
        new_total = current_total + 1
        new_rating = ((current_rating * current_total) + review.rating) / new_total
        
        worker.total_reviews = new_total
        worker.rating = round(new_rating, 1) # Làm tròn 1 chữ số thập phân (vd: 4.8)
    
    db.commit()

    return {
        "message": "✅ Đánh giá thành công! Cảm ơn bạn.",
        "new_worker_rating": worker.rating if worker else None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
# Thêm API này vào file worker-service/main.py
@app.get("/worker/{worker_id}/reviews", tags=["Review & Rating"])
async def get_worker_reviews(worker_id: str, db: Session = Depends(get_db)):
    # 1. Lấy thông tin tổng quan của thợ
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Không tìm thấy thợ")

    # 2. Lấy toàn bộ lịch sử đánh giá của thợ này
    # Sắp xếp giảm dần (desc) để đánh giá mới nhất hiện lên đầu
    reviews = db.query(Review).filter(
        Review.worker_id == worker_id
    ).order_by(Review.id.desc()).all()

    # 3. Trả về cả list đánh giá lẫn số điểm tổng quát
    return {
        "worker_id": worker.worker_id,
        "worker_name": worker.full_name,
        "average_rating": worker.rating,
        "total_reviews": worker.total_reviews,
        "reviews": reviews # Chứa mảng các comment, số sao của từng khách
    }
    
@app.websocket("/ws/notifications/{worker_id}")
async def websocket_endpoint(websocket: WebSocket, worker_id: str):
    await manager.connect(websocket, worker_id)
    try:
        while True:
            await websocket.receive_text() # Giữ kết nối
    except WebSocketDisconnect:
        manager.disconnect(worker_id)