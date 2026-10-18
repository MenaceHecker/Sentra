FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY runbooks ./runbooks

EXPOSE 8000
# Migrations run on every container start, not just the first one: alembic
# upgrade head is a no-op once the schema's already current, and this way
# a fresh deploy never needs a separate manual migration step.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"