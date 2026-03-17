# ── Stage 1: Builder ─────────────────────────────────────────────────────────
# Install dependencies in an isolated stage so build tools
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv 
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first 
COPY pyproject.toml .
COPY README.md .

# Install into an isolated prefix and copy later
RUN uv pip install --system --no-cache \
    fastapi uvicorn[standard] pydantic pydantic-settings \
    sqlalchemy aiosqlite \
    asyncpraw google-api-python-client httpx \
    groq openai \
    langchain langchain-groq langgraph \
    python-dotenv structlog aiofiles


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────

FROM python:3.12-slim AS runtime

# Non-root user — running as root in a container is a security red flag
RUN groupadd --gid 1001 appgroup && \
    useradd  --uid 1001 --gid appgroup --shell /bin/sh --create-home appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY src/ ./src/
COPY frontend/ ./frontend/ 

# Data directory with correct ownership 
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser


EXPOSE 8000

# Healthcheck — Docker/ECS/K8s will restart container if this fails
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Use exec form (not shell form) — PID 1 gets signals correctly, graceful shutdown works
CMD ["uvicorn", "src.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
