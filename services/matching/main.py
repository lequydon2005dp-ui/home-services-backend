from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
import redis
import json
import math

from shared.database import get_db

app = FastAPI(title="Matching Service API v1.0", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Kết nối Redis để đẩy thông báo realtime 
redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

# Pydantic schema nhận yêu cầu tìm thợ
class MatchRequest(BaseModel):
    order_uuid: str
    service_type: str
    lat: float
    lng: float

# Thuật toán Haversine tính khoảng cách (km) giữa 2 tọa độ GPS
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 # Bán kính Trái Đất (km)
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

@app.get("/health", tags=["health"])
async def health():
    return {"status": "🟢 MATCHING HEALTHY"}

@app.post("/matching/find", tags=["matching"])
async def find_best_worker(request: MatchRequest, db: Session = Depends(get_db)):
    # 1. Tìm tất cả thợ có kỹ năng khớp với dịch vụ khách đặt
    query = text("""
        SELECT worker_id, full_name, phone, lat, lng, rating
        FROM workers
        WHERE :service = ANY(skills)
    """)
    workers = db.execute(query, {"service": request.service_type}).fetchall()

    if not workers:
        raise HTTPException(status_code=404, detail="Hiện không có thợ nào cung cấp dịch vụ này.")

    # 2. Tính khoảng cách từ khách đến từng thợ
    eligible_workers = []
    for w in workers:
        # Bỏ qua nếu thợ chưa có tọa độ
        if w.lat is None or w.lng is None:
            continue
            
        dist = calculate_distance(request.lat, request.lng, w.lat, w.lng)
        
        # Chỉ lấy thợ trong bán kính 10km
        if dist <= 10.0:
            eligible_workers.append({
                "worker_id": w.worker_id,
                "full_name": w.full_name,
                "distance": dist,
                "rating": w.rating if w.rating else 0.0
            })

    if not eligible_workers:
        raise HTTPException(status_code=404, detail="Không có thợ nào ở gần khu vực của bạn.")

    # 3. Thuật toán sắp xếp: Ưu tiên khoảng cách gần nhất, sau đó là Rating cao nhất 
    eligible_workers.sort(key=lambda x: (x['distance'], -x['rating']))
    
    # Chọn thợ đứng đầu danh sách
    best_worker = eligible_workers[0]

    # 4. Đẩy thông báo qua Redis Pub/Sub để Worker App nhận được ngay lập tức
    notification = {
        "type": "NEW_JOB",
        "order_uuid": request.order_uuid,
        "service": request.service_type,
        "message": f"Có đơn {request.service_type} mới cách bạn {round(best_worker['distance'], 1)}km!"
    }
    
    await redis_client.publish(f"user:{best_worker['worker_id']}", json.dumps(notification))

    return {
        "message": "✅ Đã tìm thấy thợ phù hợp và gửi tín hiệu nhận việc!",
        "matched_worker": best_worker
    }