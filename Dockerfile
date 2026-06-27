FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic/ alembic/
COPY src/ src/

RUN uv sync --frozen --no-dev

CMD ["uv", "run", "sh", "-c", "alembic upgrade head && python -m bot.main"]
