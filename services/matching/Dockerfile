FROM python:3.11-slim

WORKDIR /app

# Đảm bảo copy requirements.txt trước
COPY requirements.txt .

# Cài đặt các thư viện
RUN pip install --no-cache-dir -r requirements.txt

# Copy phần còn lại của source code
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]