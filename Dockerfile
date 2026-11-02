FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "faultline.api.app:app", "--host", "0.0.0.0", "--port", "8000"]