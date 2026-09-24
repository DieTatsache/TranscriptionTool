# syntax=docker/dockerfile:1.7
# Two images from one Dockerfile:
#   target "api"    - FastAPI app (+ migrations); no speech-to-text stack
#   target "worker" - background worker with faster-whisper; CUDA libraries with WITH_CUDA=true

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
RUN groupadd --system --gid 10001 sonora \
    && useradd --system --uid 10001 --gid sonora --home-dir /app --no-create-home sonora \
    # New named volumes copy this ownership, so the non-root user can write to them.
    && mkdir -p /data /models \
    && chown sonora:sonora /data /models
WORKDIR /app


FROM base AS api-deps
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project


FROM base AS worker-deps
ARG WITH_CUDA=false
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project --extra transcription \
    && if [ "$WITH_CUDA" = "true" ]; then \
         uv pip install --python /opt/venv "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"; \
       fi


FROM base AS api
COPY --from=api-deps /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY sonora ./sonora
USER sonora
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/api/v1/health', timeout=4)"]
# Worker count via WEB_CONCURRENCY; trusted proxy IPs via FORWARDED_ALLOW_IPS (uvicorn env vars).
CMD ["uvicorn", "sonora.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]


FROM base AS worker
COPY --from=worker-deps /opt/venv /opt/venv
COPY sonora ./sonora
# Where the optional nvidia-* wheels put cuBLAS/cuDNN (harmless when absent).
ENV LD_LIBRARY_PATH=/opt/venv/lib/python3.13/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.13/site-packages/nvidia/cudnn/lib \
    HF_HOME=/models/huggingface
USER sonora
CMD ["python", "-m", "sonora.worker"]
