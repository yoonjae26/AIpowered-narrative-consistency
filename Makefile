.RECIPEPREFIX := >

.PHONY: help install dev dev-api test lint format clean

help:
>echo "NarrativeOS - Makefile Commands"
>echo "================================"
>echo "install       - Install dependencies"
>echo "dev           - Run backend API locally on server"
>echo "dev-api       - Alias for dev"
>echo "test          - Run tests"
>echo "lint          - Run linters"
>echo "format        - Format code"
>echo "clean         - Clean cache and build files"

install:
>poetry install

dev: dev-api

dev-api:
>poetry run uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload

test:
>poetry run pytest -v --cov=backend --cov-report=html

lint:
>poetry run ruff check backend/
>poetry run mypy backend/

format:
>poetry run black backend/
>poetry run ruff check --fix backend/

clean:
>find . -type d -name "__pycache__" -exec rm -rf {} +
>find . -type f -name "*.pyc" -delete
>find . -type d -name "*.egg-info" -exec rm -rf {} +
>rm -rf .pytest_cache .coverage htmlcov/
