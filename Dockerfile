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

# Lambda Runtime Interface Client — allows Lambda to call any handler via ImageConfig.Command.
# For local dev, override entrypoint: docker run --entrypoint uvicorn image apps.rag_demo.main:app ...
ENTRYPOINT ["/app/.venv/bin/python", "-m", "awslambdaric"]
CMD ["apps.rag_demo.lambda_handler.handler"]
