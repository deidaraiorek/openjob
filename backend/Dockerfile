FROM python:3.14-slim

WORKDIR /app

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/alembic.ini backend/alembic.ini
COPY backend/alembic backend/alembic
COPY backend/app backend/app
COPY backend/tests backend/tests

RUN pip install --no-cache-dir -e ./backend[dev]

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--reload"]
