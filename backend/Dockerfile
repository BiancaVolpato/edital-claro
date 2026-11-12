# syntax=docker/dockerfile:1
#
# Backend image. Build from the repository root (it also copies data/):
#   docker build -f backend/Dockerfile .                           full image
#   docker build -f backend/Dockerfile --build-arg IMAGE_VARIANT=demo .
#
# full: everything, for docker-compose and real deployments (OCR, local
#       embedding model for new analyses).
# demo: the public demonstration (DEMO_MODE=true). No PyTorch, no embedding
#       model and no Tesseract, so it fits a free 512 MB instance; it only
#       serves the analyses seeded from data/demo. See ADR-039.

ARG PYTHON_IMAGE=python:3.12-slim

# --- 1. Dependencies, installed with uv into /srv/backend/.venv ----------------
FROM ${PYTHON_IMAGE} AS deps
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ARG IMAGE_VARIANT=full
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
# The demo leaves out the embedding stack (sentence-transformers, PyTorch and the
# packages only they use); the app imports it lazily, only to analyze.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$IMAGE_VARIANT" = "demo" ]; then \
        uv sync --frozen --no-dev \
            --no-install-package sentence-transformers --no-install-package torch \
            --no-install-package transformers --no-install-package tokenizers \
            --no-install-package safetensors --no-install-package huggingface-hub \
            --no-install-package scikit-learn --no-install-package scipy \
            --no-install-package joblib --no-install-package threadpoolctl \
            --no-install-package sympy --no-install-package mpmath; \
    else \
        uv sync --frozen --no-dev; \
    fi

# --- 2. Runtime: the virtualenv, the code and the data it reads ----------------
FROM ${PYTHON_IMAGE} AS runtime
ARG IMAGE_VARIANT=full
# OCR fallback for scanned pages (full image only): Tesseract with Portuguese and
# Ghostscript, used by ocrmypdf.
RUN if [ "$IMAGE_VARIANT" = "full" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por ghostscript \
        && rm -rf /var/lib/apt/lists/*; \
    fi \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /data/uploads /data/cache/pncp /data/huggingface \
    && chown -R app:app /data

# The code expects the repository layout: backend/ next to data/.
WORKDIR /srv/backend
ENV PATH="/srv/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_DIR=/data/uploads \
    PNCP_CACHE_DIR=/data/cache/pncp \
    HF_HOME=/data/huggingface

COPY --from=deps /srv/backend/.venv .venv
COPY backend/alembic.ini ./
COPY backend/alembic alembic
COPY backend/prompts prompts
COPY backend/scripts scripts
COPY backend/app app
# Official text of the Lei 14.133 with its cached embeddings, the sample editais
# (the demo serves their PDFs), the demo snapshots and the example profile.
COPY data/law /srv/data/law
COPY data/samples /srv/data/samples
COPY data/demo /srv/data/demo
COPY data/profiles /srv/data/profiles

USER app
EXPOSE 8000

# Migrations, then demo seed or law index, then the API. PORT is set by some
# platforms (Render); docker-compose uses the default 8000.
CMD ["sh", "-c", "python scripts/prestart.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
