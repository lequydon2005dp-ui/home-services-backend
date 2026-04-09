FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn websockets redis python-socketio[client]
COPY main.py .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]