"""Index the Lei 14.133/2021 into PostgreSQL (pgvector + full-text search).

Parses data/law/L14133.html, embeds every provision with the configured
embedding model and stores them. Running it again rebuilds the index.

Usage (from the backend folder, with the database running and migrated):
    uv run python scripts/index_law.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import new_session
from app.law.index import LAW_14133, LAW_14133_FILE, index_law, law_embedder


def main() -> int:
    if not LAW_14133_FILE.exists():
        print(f"Arquivo da lei não encontrado: {LAW_14133_FILE}")
        print("Veja data/law/README.md para saber como obtê-lo.")
        return 1

    # Vectors come from the committed cache; the model is only loaded (and the
    # cache updated) if the law text or the embedding model changed.
    embedder = law_embedder()

    started = time.perf_counter()
    session = new_session()
    try:
        count = index_law(session, LAW_14133_FILE.read_bytes(), embedder)
    finally:
        session.close()
    if embedder.save():
        print("Cache de embeddings atualizado: data/law/L14133.embeddings.npz")
    print(f"{LAW_14133}: {count} dispositivos indexados em {time.perf_counter() - started:.0f} s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
