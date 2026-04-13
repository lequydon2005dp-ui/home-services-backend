# services/review/main.py - CODE MỚI (IN-MEMORY)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

app = FastAPI(title="Review Service")
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory database
reviews_db: List[dict] = []

class ReviewCreate(BaseModel):
    order_id: str
    worker_id: str
    rating: float
    comment: Optional[str] = None

class ReviewResponse(BaseModel):
    id: int
    order_id: str
    worker_id: str
    rating: float
    comment: Optional[str] = None
    created_at: datetime

@app.post("/review/create", response_model=ReviewResponse)
def create_review(review: ReviewCreate):
    if review.rating < 1.0 or review.rating > 5.0:
        raise HTTPException(status_code=400, detail="Rating must be between 1.0 and 5.0")
    
    new_review = {
        "id": len(reviews_db) + 1,
        "order_id": review.order_id,
        "worker_id": review.worker_id,
        "rating": review.rating,
        "comment": review.comment,
        "created_at": datetime.now()
    }
    reviews_db.append(new_review)
    return new_review

@app.get("/review/worker/{worker_id}")
def get_worker_reviews(worker_id: str):
    worker_reviews = [r for r in reviews_db if r["worker_id"] == worker_id]
    if not worker_reviews:
        return {"reviews": [], "average_rating": 0.0, "total": 0}
    
    avg_rating = sum(r["rating"] for r in worker_reviews) / len(worker_reviews)
    return {
        "reviews": worker_reviews,
        "average_rating": round(avg_rating, 1),
        "total": len(worker_reviews)
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "total_reviews": len(reviews_db)}

@app.get("/")
def root():
    return {"message": "Review Service is running!"}