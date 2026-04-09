from fastapi import FastAPI, HTTPException, BackgroundTasks
import redis.asyncio as redis
import hashlib
import hmac
import json
import os
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Payment Service")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

MOMO_PARTNER = os.getenv("MOMO_PARTNER")
MOMO_ACCESS_KEY = os.getenv("MOMO_ACCESS_KEY")
MOMO_SECRET_KEY = os.getenv("MOMO_SECRET_KEY")

@app.post("/payment/momo/create")
async def create_momo_payment(amount: float, order_id: str, user_id: str):
    if not all([MOMO_PARTNER, MOMO_ACCESS_KEY, MOMO_SECRET_KEY]):
        raise HTTPException(500, "Payment config not set")
    
    endpoint = "https://test-payment.momo.vn/gw_payment/transactionProcessor"
    
    data = {
        "partnerCode": MOMO_PARTNER,
        "accessKey": MOMO_ACCESS_KEY,
        "requestId": str(datetime.now().timestamp()),
        "amount": int(amount * 100),
        "orderId": order_id,
        "orderInfo": f"Thanh toan don hang {order_id}",
        "returnUrl": "http://localhost:3000/payment/return",
        "notifyUrl": "http://localhost:8006/payment/notify",
        "requestType": "captureMoMoWallet",
        "extraData": user_id
    }
    
    raw_signature = "&".join([f"{k}={v}" for k, v in sorted(data.items())])
    signature = hmac.new(
        MOMO_SECRET_KEY.encode(),
        raw_signature.encode(),
        hashlib.sha256
    ).hexdigest()
    
    data["signature"] = signature
    
    return {"payment_url": endpoint, "data": data}

@app.post("/payment/notify")
async def momo_ipn(request: dict):
    """Momo IPN callback"""
    try:
        # Verify signature (simplified)
        order_id = request.get("orderId")
        amount = request.get("amount")
        result_code = request.get("resultCode")
        
        if result_code == "0":  # Success
            # Notify user
            await redis_client.publish(
                f"user:{request.get('extraData')}", 
                json.dumps({
                    "type": "payment_success",
                    "order_id": order_id,
                    "amount": int(amount) / 100,
                    "status": "completed"
                })
            )
        
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}