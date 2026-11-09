FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
ARG PYTHON_EXTRAS=ml,pdf
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY src ./src
COPY apps ./apps
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir ".[${PYTHON_EXTRAS}]"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
