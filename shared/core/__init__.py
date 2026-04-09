from pydantic_settings import BaseSettings
from typing import Optional

class Settings (BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379"
    ELATICSEARCH_URL: str = "http:/localhost:9200"
    JWWT_SECRET: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        
Settings = Settings()