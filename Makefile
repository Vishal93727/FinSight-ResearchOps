.PHONY: test lint typecheck api worker web-build compose-up compose-down

test:
	python -m pytest

lint:
	ruff check backend src apps

typecheck:
	mypy backend src apps

api:
	PYTHONPATH=src:backend uvicorn app.main:app --app-dir backend --reload

worker:
	celery -A apps.worker.celery_app:celery_app worker --loglevel=INFO

web-build:
	cd apps/web && npm run build

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down
