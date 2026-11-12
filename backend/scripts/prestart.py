"""Prepares the database before the API starts (used by the Docker image).

1. Applies the migrations.
2. In demo mode, loads the demo snapshots (no LLM, no embedding model).
   Otherwise, rebuilds the law index from the committed embeddings cache; if
   that fails the API still starts and only the law search is unavailable.

Usage (from the backend folder):
    python scripts/prestart.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run(*args: str) -> int:
    return subprocess.call([sys.executable, *args], cwd=BACKEND_DIR)


def main() -> int:
    if run("-m", "alembic", "upgrade", "head") != 0:
        return 1
    if get_settings().demo_mode:
        return run("scripts/demo.py", "seed")
    if run("scripts/index_law.py") != 0:
        print("AVISO: a lei não foi indexada; a busca na lei fica indisponível.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
