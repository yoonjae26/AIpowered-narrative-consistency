.PHONY: help install dev test lint format clean docker-build docker-up docker-down

help:
@echo "NarrativeOS - Makefile Commands"
@echo "================================"
@echo "install       - Install dependencies"
@echo "dev           - Run development server"
@echo "test          - Run tests"
@echo "lint          - Run linters"
@echo "format        - Format code"
@echo "clean         - Clean cache and build files"
@echo "docker-build  - Build Docker containers"
@echo "docker-up     - Start Docker services"
@echo "docker-down   - Stop Docker services"

install:
poetry install

dev:
docker-compose -f infrastructure/docker/docker-compose.dev.yml up

test:
poetry run pytest -v --cov=backend --cov-report=html

lint:
poetry run ruff check backend/
poetry run mypy backend/

format:
poetry run black backend/
poetry run ruff check --fix backend/

clean:
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
find . -type d -name "*.egg-info" -exec rm -rf {} +
rm -rf .pytest_cache .coverage htmlcov/

docker-build:
docker-compose -f infrastructure/docker/docker-compose.dev.yml build

docker-up:
docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d

docker-down:
docker-compose -f infrastructure/docker/docker-compose.dev.yml down
