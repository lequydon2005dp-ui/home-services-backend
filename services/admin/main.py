from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import List, Dict
import random

app = FastAPI(title="Admin Service")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/admin/stats")
def admin_stats():
    return {
        "total_users": 1523,
        "total_orders": 3567,
        "revenue_today": 25340000,
        "revenue_month": 750000000,
        "pending_orders": 42,
        "active_workers": 89,
        "updated_at": datetime.utcnow().isoformat()
    }

@app.get("/admin/workers") 
def admin_workers(limit: int = 10) -> List[Dict]:
    workers = []
    for i in range(1, limit + 1):
        workers.append({
            "id": i,
            "name": f"Worker {i}",
            "rating": round(random.uniform(3.5, 5.0), 1),
            "orders_completed": random.randint(50, 200),
            "revenue": random.randint(5000000, 25000000),
            "status": random.choice(["active", "busy", "offline"])
        })
    return workers

@app.get("/admin/orders/pending")
def pending_orders():
    return {
        "pending": 42,
        "in_progress": 23,
        "completed_today": 156
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}