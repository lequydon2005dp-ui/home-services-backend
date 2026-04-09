.PHONY: install dev up down logs migrate test lint format clean

install:
	pip install -r requirements.txt

dev:
	docker-compose up -d postgres redis elasticsearch
	sleep 30
	docker-compose up auth-service

up:
	docker-compose up --build

down:
	docker-compose down -v

logs:
	docker-compose logs -f

migrate:
	docker-compose exec auth-service alembic upgrade head

test:
	docker-compose up -d postgres redis
	pytest tests/ -v --cov=services

lint:
	flake8 services/
	isort services/
	black services/

format:
	isort services/
	black services/

clean:
	docker-compose down -v
	docker system prune -f