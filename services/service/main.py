from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, Text
from shared.database import engine, Base, get_db
from pydantic import BaseModel
from elasticsearch import Elasticsearch
import os

app = FastAPI(title="Service Management API")

# Kết nối Elasticsearch
es = Elasticsearch(os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200"))

# --- Database Model ---
class ServiceItem(Base):
    __tablename__ = "service_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True)
    category = Column(String(50), index=True)
    description = Column(Text)
    base_price = Column(Float)

Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas ---
class ServiceCreate(BaseModel):
    name: str
    category: str
    description: str
    base_price: float

@app.post("/services/", tags=["Admin"])
async def create_service(item: ServiceCreate, db: Session = Depends(get_db)):
    # 1. Lưu vào PostgreSQL
    db_item = ServiceItem(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    
    # 2. Đồng bộ sang Elasticsearch để tìm kiếm
    es_body = {
        "name": db_item.name,
        "category": db_item.category,
        "description": db_item.description,
        "base_price": db_item.base_price
    }
    es.index(index="services", id=str(db_item.id), document=es_body)
    
    return {"message": "✅ Dịch vụ đã được tạo và đồng bộ sang ES", "data": db_item}

@app.get("/services/search", tags=["Customer"])
async def search_services(q: str):
    # Tìm kiếm trên Elasticsearch (Search mờ, search theo mô tả)
    query = {
        "multi_match": {
            "query": q,
            "fields": ["name^3", "category^2", "description"] # Name được ưu tiên gấp 3 lần
        }
    }
    res = es.search(index="services", query=query)
    results = [hit["_source"] for hit in res["hits"]["hits"]]
    return results