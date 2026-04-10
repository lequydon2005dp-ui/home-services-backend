from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, Float, DateTime
from shared.database import engine, Base, get_db
from pydantic import BaseModel
from datetime import datetime
import httpx
import json
import redis.asyncio as redis
from sqlalchemy import func

app = FastAPI(title="Payment Service API")
redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. Database Model cho Lịch sử giao dịch ---
class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    order_uuid = Column(String(50), index=True)
    amount = Column(Float)
    payment_method = Column(String(20), default="VNPAY")
    status = Column(String(20), default="pending") # pending, success, failed
    transaction_code = Column(String(100), nullable=True) # Mã GD của VNPay trả về
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- 2. Schemas ---
class PaymentCreate(BaseModel):
    order_uuid: str
    amount: float

class VNPayWebhook(BaseModel):
    order_uuid: str
    status: str
    transaction_code: str

class CODRequest(BaseModel):
    order_uuid: str
    worker_id: str
    amount: float

# --- 3. API Khởi tạo thanh toán ---
@app.post("/payment/create-url", tags=["Payment Checkout"])
async def create_payment_url(req: PaymentCreate, db: Session = Depends(get_db)):
    # 1. Lưu giao dịch vào Database với trạng thái 'pending'
    new_trans = Transaction(order_uuid=req.order_uuid, amount=req.amount, status="pending")
    db.add(new_trans)
    db.commit()

    # 2. Sinh URL thanh toán (Giả lập thuật toán mã hóa VNPAY)
    mock_vnpay_url = f"https://sandbox.vnpayment.vn/checkout?amount={int(req.amount)}&order_id={req.order_uuid}"

    return {
        "message": "🔗 Link thanh toán đã được tạo",
        "checkout_url": mock_vnpay_url,
        "transaction_status": new_trans.status
    }
    
@app.on_event("startup")
async def startup_event():
    # Kiểm tra xem Redis có online không
    try:
        await redis_client.ping()
        print("✅ Payment Service đã kết nối được với Redis!")
    except Exception as e:
        print(f"❌ Không thể kết nối Redis: {e}")

# --- 4. API Webhook (Dành cho VNPay gọi vào khi khách đã quét mã) ---
@app.post("/payment/webhook", tags=["Payment Webhook"])
async def vnpay_ipn_webhook(data: VNPayWebhook, db: Session = Depends(get_db)):
    # 1. Cập nhật trạng thái giao dịch trong bảng Transactions
    transaction = db.query(Transaction).filter(Transaction.order_uuid == data.order_uuid).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Giao dịch không tồn tại")
    
    transaction.status = data.status
    transaction.transaction_code = data.transaction_code
    db.commit()

    # 2. Quan trọng: Nếu tiền vào (success), gọi sang Order Service để cập nhật trạng thái đơn!
    if data.status == "success":
        try:
            order_api_url = f"http://order-service:8000/order/{data.order_uuid}/status"
            payload = {"status": "paid", "worker_id": "SYSTEM"} 
            
            # CÚ PHÁP CHUẨN ASYNC:
            async with httpx.AsyncClient() as client:
                response = await client.put(order_api_url, json=payload)
                
            if response.status_code == 200:
                print(f"✅ Đơn {data.order_uuid} ĐÃ THỰC SỰ LÊN PAID!")
            else:
                print(f"⚠️ Kêu Order nhưng bị chửi: {response.text}")
            
            review_notif = {
                "event": "REQUEST_REVIEW",
                "order_uuid": data.order_uuid,
                "message": "🌟 Tuyệt vời! Đơn hàng đã thanh toán. Mời bạn đánh giá chất lượng thợ nhé!"
            }
            # Giả sử Đôn bắn vào kênh chung hoặc kênh riêng của khách
            await redis_client.publish(f"user:customer_{data.order_uuid}", json.dumps(review_notif))
            
        except Exception as e:
            print(f"⚠️ Lỗi kết nối Order: {e}")

    return {"message": "Webhook nhận dữ liệu thành công", "status": "200 OK"}

# --- API Xác nhận thu tiền mặt (Dành cho App của Thợ) ---
@app.post("/payment/cod", tags=["Payment Checkout"])
async def process_cod_payment(req: CODRequest, db: Session = Depends(get_db)):
    
    existing_trans = db.query(Transaction).filter(
        Transaction.order_uuid == req.order_uuid,
        Transaction.status == "success"  # Chỉ chặn nếu đã thành công
    ).first()
    
    if existing_trans:
        raise HTTPException(
            status_code=400, 
            detail=f"Đơn hàng này đã được thanh toán bằng {existing_trans.payment_method} rồi! Không thể thu tiền thêm."
        )
        
    # 1. Lưu giao dịch vào Database
    # Cực kỳ quan trọng để Admin biết thợ nào đang cầm tiền mặt của hệ thống
    new_trans = Transaction(
        order_uuid=req.order_uuid,
        amount=req.amount,
        payment_method="COD",
        status="success", # Tiền trao cháo múc nên status là success luôn
        transaction_code=f"COD-{req.worker_id}-{int(datetime.utcnow().timestamp())}"
    )
    db.add(new_trans)
    db.commit()

    # 2. Gọi sang Order Service để cập nhật trạng thái đơn thành 'paid'
    try:
        order_api_url = f"http://order-service:8000/order/{req.order_uuid}/status"
        # Bắn status 'paid' và kèm theo worker_id để order-service cho phép cập nhật
        payload = {"status": "paid", "worker_id": req.worker_id}
        async with httpx.AsyncClient() as client:
            response = await client.put(order_api_url, json=payload)
        
        if response.status_code == 200:
            print(f"✅ Đơn {req.order_uuid} ĐÃ THỰC SỰ LÊN PAID!")
            review_notif = {
            "event": "REQUEST_REVIEW",
            "order_uuid": req.order_uuid,
            "message": "💵 Bạn đã thanh toán tiền mặt. Đừng quên đánh giá thợ 5 sao nếu bạn hài lòng nhé!"
            }
            await redis_client.publish(f"user:customer_{req.order_uuid}", json.dumps(review_notif))
        else:
            print(f"⚠️ Kêu Order nhưng bị chửi: {response.text}")
    except Exception as e:
        print(f"⚠️ Lỗi kết nối: {e}")

    return {
        "message": "💵 Xác nhận thu tiền mặt thành công! Đơn hàng đã hoàn tất.",
        "order_uuid": req.order_uuid,
        "payment_method": "COD",
        "collected_by": req.worker_id
    }
    
@app.get("/admin/revenue/stats", tags=["Admin Dashboard"])
async def get_revenue_stats(db: Session = Depends(get_db)):
    # 1. Tính tổng tiền theo từng phương thức thanh toán
    stats = db.query(
        Transaction.payment_method,
        func.sum(Transaction.amount).label("total_amount"),
        func.count(Transaction.id).label("transaction_count")
    ).filter(Transaction.status == "success").group_by(Transaction.payment_method).all()

    # 2. Định dạng lại dữ liệu trả về cho đẹp
    report = {item.payment_method: {"total": item.total_amount, "count": item.transaction_count} for item in stats}
    
    total_revenue = sum(item.total_amount for item in stats)
    
    return {
        "status": "success",
        "total_revenue": total_revenue,
        "detail": report,
        "generated_at": datetime.utcnow()
    }
    
@app.get("/payment/history/{order_uuid}", tags=["Payment History"])
async def get_payment_history(order_uuid: str, db: Session = Depends(get_db)):
    # Lấy lịch sử giao dịch của một đơn hàng cụ thể (FR23)
    history = db.query(Transaction).filter(Transaction.order_uuid == order_uuid).all()
    if not history:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch sử giao dịch cho đơn này")
    return history