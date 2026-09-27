# Drivkraft Tax server: FastAPI (/api) + MCP (/mcp) + the pinned OpenTax binary and
# otd-spec checkout, for the hosted demo on Fly.io (planning/02, "Demo").
# The web app is deployed separately (Vercel) and proxies /api here.
FROM python:3.11-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python3.11

# Dependencies first so code changes don't re-fetch them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Pinned upstreams (otd-spec, OpenTax + its Linux release binary), then the app.
COPY scripts/ scripts/
RUN BOOTSTRAP_UV_ARGS="--frozen --no-dev --no-install-project" bash scripts/bootstrap.sh
COPY server/ server/
COPY reference/ reference/
RUN uv sync --frozen --no-dev

ENV DRIVKRAFT_DATA=/data \
    DRIVKRAFT_HOST=0.0.0.0 \
    DRIVKRAFT_PORT=8080 \
    DRIVKRAFT_DEMO=1 \
    PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
CMD ["drivkraft-tax-server"]
