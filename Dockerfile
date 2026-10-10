# ZeroDrop: dashboard API + built UI in one image. Keys are never baked in; pass them at runtime.

# Stage 1: build the dashboard
FROM node:24-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# Stage 2: Python runtime managed by uv
FROM python:3.13-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Dependencies first so code changes do not invalidate this layer
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY scenarios/ scenarios/
RUN uv sync --frozen --no-dev
COPY --from=ui /ui/dist ui/dist

# The commit the image was built from (the container has no .git); shown in run outcomes
ARG GIT_COMMIT=""
ENV ZERODROP_GIT_COMMIT=${GIT_COMMIT}

RUN useradd --create-home --uid 10001 zerodrop \
    && mkdir -p /app/runs && chown -R zerodrop:zerodrop /app/runs
USER zerodrop

EXPOSE 8700
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8700/api/meta', timeout=2).status == 200 else 1)"

CMD ["zerodrop", "serve", "--host", "0.0.0.0", "--port", "8700", "--planner", "oracle", "--db", "/app/runs/zerodrop.db"]
