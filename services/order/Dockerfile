FROM python:3.11-slim

WORKDIR /app

# 1. Copy requirements TRƯỚC
COPY requirements.txt .

# 2. Install deps TRƯỚC copy code
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy source code SAU
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]