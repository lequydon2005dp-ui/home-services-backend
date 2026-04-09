from fastapi import FastAPI
from sqlalchemy import Column, Float, Integer, String, ForeignKey
from shared.database import Base, engine

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    worker_id = Column(Integer, ForeignKey("workers.id"))
    rating = Column(Float)  # 1-5
    comment = Column(String)

Base.metadata.create_all(engine)

@app.post("/review/create")
def create_review(order_id: int, worker_id: int, rating: float, comment: str):
    return {"message": "Review saved", "rating": rating}