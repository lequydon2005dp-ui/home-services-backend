from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/home_services")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

settings = Settings()