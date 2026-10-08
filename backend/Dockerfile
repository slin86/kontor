FROM python:3.13-slim
LABEL org.opencontainers.image.source="https://github.com/slin86/kontor"

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --no-create-home kontor
# numeric, so Kubernetes can verify runAsNonRoot
USER 10001

ARG APP_VERSION=dev
ENV KONTOR_VERSION=$APP_VERSION
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
# Migrations run on every start; trust the proxy in front for the client address and scheme.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn kontor.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
