from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, Float, Text
from shared.database import engine, Base, get_db
from pydantic import BaseModel
# 1. Thay đổi: Import AsyncElasticsearch và exceptions để bắt lỗi
from elasticsearch import AsyncElasticsearch, exceptions as es_exceptions
import os
from typing import Optional

app = FastAPI(title="Service Management API")

# 2. Thay đổi: Khởi tạo client bất đồng bộ (Async client)
es = AsyncElasticsearch(os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = None

# --- API Add dịch vụ ---
@app.post("/services/", tags=["Admin"])
async def create_service(item: ServiceCreate, db: Session = Depends(get_db)):
    # 1. Lưu vào PostgreSQL
    db_item = ServiceItem(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    
    # 2. Đồng bộ sang Elasticsearch (Có bảo vệ bằng try-except)
    es_body = {
        "name": db_item.name,
        "category": db_item.category,
        "description": db_item.description,
        "base_price": db_item.base_price
    }
    
    try:
        # 3. Thay đổi: Thêm chữ 'await' vì gọi hàm async
        await es.index(index="services", id=str(db_item.id), document=es_body)
    except Exception as e:
        # Nếu ES lỗi, báo cho Admin biết để xử lý (DB vẫn giữ được dữ liệu)
        return {
            "message": "⚠️ Đã tạo trong Postgres nhưng lỗi đồng bộ sang Elasticsearch!", 
            "error_detail": str(e),
            "data": db_item
        }
    
    return {"message": "✅ Dịch vụ đã được tạo và đồng bộ sang ES", "data": db_item}
# --- API Sửa dịch vụ ---
@app.put("/services/{service_id}", tags=["Admin"])
async def update_service(service_id: int, item: ServiceUpdate, db: Session = Depends(get_db)):
    # 1. Tìm dịch vụ trong PostgreSQL
    db_item = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Không tìm thấy dịch vụ")

    # 2. Cập nhật các trường có thay đổi vào DB
    update_data = item.model_dump(exclude_unset=True) # Chỉ lấy các trường user có gửi lên
    for key, value in update_data.items():
        setattr(db_item, key, value)
    
    db.commit()
    db.refresh(db_item)

    # 3. Đồng bộ dữ liệu mới sang Elasticsearch (Dùng lại lệnh index để đè dữ liệu cũ)
    es_body = {
        "name": db_item.name,
        "category": db_item.category,
        "description": db_item.description,
        "base_price": db_item.base_price
    }
    try:
        await es.index(index="services", id=str(db_item.id), document=es_body)
    except Exception as e:
        print(f"⚠️ Đã sửa trong DB nhưng lỗi đồng bộ ES: {e}")

    return {"message": "✅ Đã cập nhật dịch vụ thành công", "data": db_item}

# --- API Xóa dịch vụ ---
@app.delete("/services/{service_id}", tags=["Admin"])
async def delete_service(service_id: int, db: Session = Depends(get_db)):
    # 1. Tìm và xóa trong PostgreSQL
    db_item = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Không tìm thấy dịch vụ")

    db.delete(db_item)
    db.commit()

    # 2. Đồng thời "tiêu diệt" nó trên Elasticsearch
    try:
        await es.delete(index="services", id=str(service_id))
    except es_exceptions.NotFoundError:
        pass # Nếu ES chưa kịp lưu mà đã xóa thì bỏ qua lỗi này
    except Exception as e:
        print(f"⚠️ Đã xóa trong DB nhưng lỗi xóa ES: {e}")

    return {"message": "🗑️ Đã xóa dịch vụ vĩnh viễn khỏi hệ thống"}

# --- API Xem dịch vụ bên Người Dùng ---
@app.get("/services/", tags=["Customer"])
async def get_services(
    category: Optional[str] = None, # FR6: Cho phép truyền category (không bắt buộc)
    limit: int = 10,  # Phân trang
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(ServiceItem)
    
    # Nếu khách có chọn danh mục, thì thêm điều kiện lọc
    if category:
        query = query.filter(ServiceItem.category == category)
        
    # Lấy danh sách kèm phân trang
    services = query.offset(offset).limit(limit).all()
    
    return {"status": "success", "data": services}

@app.get("/services/search", tags=["Customer"])
async def search_services(q: str):
    query = {
        "multi_match": {
            "query": q,
            "fields": ["name^3", "category^2", "description"] 
        }
    }
    
    try:
        # 4. Thay đổi: Thêm 'await'
        res = await es.search(index="services", query=query)
        results = [hit["_source"] for hit in res["hits"]["hits"]]
        return results
        
    except es_exceptions.NotFoundError:
        # Bắt lỗi an toàn nếu index 'services' chưa hề được tạo (chưa có data nào)
        return [] 
    except Exception as e:
        # Bắt các lỗi khác (như mất kết nối ES) để tránh app bị crash

        raise HTTPException(status_code=503, detail=f"Dịch vụ tìm kiếm đang gián đoạn: {str(e)}")
