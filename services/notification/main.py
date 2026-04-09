from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis # Sử dụng thư viện redis bất đồng bộ (async)
import json
import asyncio
from typing import Dict

app = FastAPI(title="Notification Service (Real-time) v1.0", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Quản lý các kết nối WebSocket đang mở của Worker
class ConnectionManager:
    def __init__(self):
        # Lưu trữ theo dạng: {"worker_id_1": websocket_1, "worker_id_2": websocket_2}
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, worker_id: str):
        await websocket.accept()
        self.active_connections[worker_id] = websocket
        print(f"🟢 Thợ {worker_id} đã kết nối WebSocket!")

    def disconnect(self, worker_id: str):
        if worker_id in self.active_connections:
            del self.active_connections[worker_id]
            print(f"🔴 Thợ {worker_id} đã ngắt kết nối.")

    async def send_personal_message(self, message: str, worker_id: str):
        if worker_id in self.active_connections:
            websocket = self.active_connections[worker_id]
            await websocket.send_text(message)

manager = ConnectionManager()

# --- Endpoint cho WebSocket ---
@app.websocket("/ws/{worker_id}")
async def websocket_endpoint(websocket: WebSocket, worker_id: str):
    await manager.connect(websocket, worker_id)
    try:
        while True:
            # Nhận tin nhắn (ping) từ client để giữ kết nối
            data = await websocket.receive_text()
            # Có thể xử lý tin nhắn từ app Worker ở đây nếu cần
            
    except WebSocketDisconnect:
        manager.disconnect(worker_id)


# --- Redis Pub/Sub Listener ---
async def redis_listener():
    # Kết nối tới Redis (sử dụng async)
    r = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
    pubsub = r.pubsub()
    
    # Đăng ký nghe tất cả các kênh có dạng user:* (ví dụ: user:0868327457)
    await pubsub.psubscribe('user:*')
    print("🎧 Notification Service đang lắng nghe tín hiệu từ Redis...")

    while True:
        try:
            # Lấy tin nhắn mới nhất
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                # message['channel'] sẽ có dạng 'user:0868327457'
                channel = message['channel']
                worker_id = channel.split(':')[1] # Lấy ID thợ
                data = message['data']
                
                print(f"🚀 Nhận job mới cho {worker_id}: {data}")
                
                # Bắn qua WebSocket cho người thợ đó
                await manager.send_personal_message(data, worker_id)
                
            await asyncio.sleep(0.01) # Tránh treo vòng lặp
        except Exception as e:
            print(f"❌ Lỗi Redis Listener: {e}")
            await asyncio.sleep(1)

# Chạy Redis Listener ngầm khi FastAPI khởi động
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_listener())

@app.get("/health", tags=["health"])
async def health():
    return {"status": "🟢 NOTIFICATION (WS) HEALTHY"}