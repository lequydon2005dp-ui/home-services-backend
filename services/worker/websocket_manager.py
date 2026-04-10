from fastapi import WebSocket
import json

class ConnectionManager:
    def __init__(self):
        # Lưu trữ: {worker_id: websocket_connection}
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, worker_id: str):
        await websocket.accept()
        self.active_connections[worker_id] = websocket
        print(f"🟢 Thợ {worker_id} đã kết nối WebSocket")

    def disconnect(self, worker_id: str):
        if worker_id in self.active_connections:
            del self.active_connections[worker_id]
            print(f"🔴 Thợ {worker_id} đã thoát")

    async def broadcast(self, message: dict):
        # Gửi tin nhắn cho tất cả thợ đang online
        for connection in self.active_connections.values():
            await connection.send_json(message)

manager = ConnectionManager()