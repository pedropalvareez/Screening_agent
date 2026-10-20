FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# Dependencies first so this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY src ./src
COPY config ./config

RUN useradd --create-home app
USER app

EXPOSE 8000
CMD ["uvicorn", "sazon.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
