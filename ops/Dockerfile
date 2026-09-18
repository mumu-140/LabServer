ARG PYTHON_VERSION=3.13-slim

# ------------------------------------------------------------------------------
# Builder Stage
# ------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS builder

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG http_proxy
ARG https_proxy

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests and workspace members
COPY pyproject.toml uv.lock .python-version ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps

# Install all workspace packages and locked production dependencies into /app/.venv
RUN uv sync --all-packages --frozen --no-dev

# ------------------------------------------------------------------------------
# Production Runtime Stage
# ------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Create non-root user matching host UID 1000
RUN groupadd -g 1000 labserver && \
    useradd -u 1000 -g labserver -m -s /bin/bash labserver && \
    mkdir -p /data && \
    chown -R labserver:labserver /data

WORKDIR /app

# Copy virtual environment and project sources from builder
COPY --from=builder --chown=labserver:labserver /app/.venv /app/.venv
COPY --from=builder --chown=labserver:labserver /app/packages /app/packages
COPY --from=builder --chown=labserver:labserver /app/services /app/services
COPY --from=builder --chown=labserver:labserver /app/apps /app/apps
COPY --from=builder --chown=labserver:labserver /app/pyproject.toml /app/uv.lock ./

COPY --chown=labserver:labserver ops/entrypoint-core.sh /app/ops/entrypoint-core.sh
RUN chmod +x /app/ops/entrypoint-core.sh

USER labserver

EXPOSE 18280 18281

CMD ["uvicorn", "labserver_core.app:app", "--host", "0.0.0.0", "--port", "18281"]
