FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first — layer is cached unless these change
COPY pyproject.toml uv.lock ./

# Install production dependencies only (no dev/test tools)
RUN uv sync --frozen --no-dev

# Copy application source
COPY aiplatform/ ./aiplatform/
COPY apps/ ./apps/
COPY migrations/ ./migrations/
COPY alembic.ini ./

EXPOSE 8000

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "apps.rag_demo.main:app", "--host", "0.0.0.0", "--port", "8000"]
