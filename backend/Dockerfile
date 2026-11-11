# Development image. A slimmer multi-stage build comes with the deploy stage.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

# OCR fallback for scanned pages: Tesseract (with Portuguese) and Ghostscript, used by ocrmypdf.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por ghostscript \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Install dependencies first so this layer is cached while only source code changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000

# Migrations run on start so "docker compose up" always yields a ready database.
# The law index is rebuilt too (about 2 s, from the cached embeddings). If the law
# files are not mounted, the API still starts and only the law search is unavailable.
CMD ["sh", "-c", "alembic upgrade head && (python scripts/index_law.py || echo 'WARNING: law not indexed') && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
