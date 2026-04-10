from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
import json
import asyncio
from typing import Dict

app = FastAPI(title="Notification Service (Real-time) v1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Quản lý kết nối WebSocket ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, worker_id: str):
        await websocket.accept()
        self.active_connections[worker_id] = websocket
        print(f"🟢 Thợ {worker_id} đã kết nối WebSocket!")

    def disconnect(self, worker_id: str):
        if worker_id in self.active_connections:
            del self.active_connections[worker_id]
            print(f"🔴 Thợ {worker_id} đã ngắt kết nối.")

    async def send_json_message(self, message: dict, worker_id: str):
        if worker_id in self.active_connections:
            await self.active_connections[worker_id].send_json(message)

    async def broadcast(self, message: dict):
        for worker_id in self.active_connections:
            await self.active_connections[worker_id].send_json(message)

manager = ConnectionManager()

# --- Redis Pub/Sub Listener (Trái tim của Service) ---
async def redis_listener():
    r = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
    pubsub = r.pubsub()
    
    # 📻 Nghe cả kênh riêng (user:*) và kênh chung (broadcast:workers)
    await pubsub.psubscribe('user:*')
    await pubsub.subscribe('broadcast:workers')
    
    print("🎧 Notification Service đang trực chiến trên Redis...")

    async for message in pubsub.listen():
        if message["type"] in ["message", "pmessage"]:
            channel = message['channel']
            data = json.loads(message['data'])
            
            # TRƯỜNG HỢP 1: Gửi đích danh (user:worker123)
            if channel.startswith("user:"):
                worker_id = channel.split(':')[1]
                print(f"📧 Thư riêng cho {worker_id}: {data}")
                await manager.send_json_message(data, worker_id)
            
            # TRƯỜNG HỢP 2: Loa phường (Gửi cho tất cả)
            elif channel == "broadcast:workers":
                print(f"📢 Loa phường thông báo: {data}")
                await manager.broadcast(data)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_listener())

@app.websocket("/ws/{worker_id}")
async def websocket_endpoint(websocket: WebSocket, worker_id: str):
    await manager.connect(websocket, worker_id)
    try:
        while True:
            await websocket.receive_text() # Giữ kết nối
    except WebSocketDisconnect:
        manager.disconnect(worker_id)

@app.get("/health")
async def health():
    return {"status": "🟢 NOTIFICATION (WS) HEALTHY", "online_workers": list(manager.active_connections.keys())}