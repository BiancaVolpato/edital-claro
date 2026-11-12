"""Demo data: seed, reset, export and generate the analyses of the public demo.

Commands (from the backend folder, with the database running and migrated):
    uv run python scripts/demo.py seed
        Loads every snapshot of data/demo/ that is not in the database yet.
        No LLM, no embedding model. Runs on every start of the demo server.
    uv run python scripts/demo.py reset --yes
        Deletes documents, analyses, profiles and eligibility checks (and the
        stored PDFs), then seeds again. The law index is kept.
    uv run python scripts/demo.py export ANALYSIS_ID NAME
        Writes the analysis (and its eligibility checks) to data/demo/NAME.json.
    uv run python scripts/demo.py generate --yes
        Analyzes the demo editais with the real LLM, checks the example profile
        against each and writes their snapshots. Needs ANTHROPIC_API_KEY and
        costs money (each analysis is capped by ANALYSIS_MAX_COST_USD).
"""

import argparse
import datetime as dt
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import Analysis
from app.db.session import new_session
from app.demo.snapshots import (
    DEMO_DIR,
    DEMO_SAMPLES,
    SAMPLES_DIR,
    SnapshotError,
    analyze_sample,
    clear_data,
    example_profile,
    export_snapshot,
    seed,
    write_snapshot,
)
from app.llm.base import LLMNotConfiguredError
from app.llm.factory import get_llm_provider


def cmd_seed() -> int:
    with new_session() as session:
        result = seed(session)
    if not result.loaded and not result.skipped:
        print(f"Nenhum snapshot em {DEMO_DIR}. Gere com: just demo-generate")
    for name in result.loaded:
        print(f"Carregado: {name}")
    for name in result.skipped:
        print(f"Já estava no banco: {name}")
    return 0


def cmd_reset(confirmed: bool) -> int:
    if not confirmed:
        print("Isto apaga todos os documentos, análises e perfis do banco em DATABASE_URL.")
        print("Para confirmar, rode de novo com --yes.")
        return 2
    with new_session() as session:
        counts = clear_data(session)
    print("Apagado: " + ", ".join(f"{table} {count}" for table, count in counts.items()))
    return cmd_seed()


def cmd_export(analysis_id: str, name: str) -> int:
    with new_session() as session:
        analysis = session.get(Analysis, uuid.UUID(analysis_id))
        if analysis is None:
            print(f"Análise {analysis_id} não encontrada.")
            return 1
        snapshot = export_snapshot(session, analysis)
    path = DEMO_DIR / f"{name}.json"
    write_snapshot(snapshot, path)
    print(f"Snapshot gravado em {path}")
    return 0


def cmd_generate(confirmed: bool, names: list[str]) -> int:
    limit = get_settings().analysis_max_cost_usd
    if not confirmed:
        print(f"Isto analisa {len(names)} editais com a IA real e custa dinheiro")
        print(f"(até US$ {limit:.2f} por análise). Para confirmar, rode de novo com --yes.")
        return 2
    try:
        llm = get_llm_provider()
    except LLMNotConfiguredError:
        print("Defina ANTHROPIC_API_KEY no .env para gerar os snapshots.")
        return 1
    with new_session() as session:
        profile = example_profile(session)
        for name in names:
            print(f"Analisando {name}...")
            analysis = analyze_sample(
                session, SAMPLES_DIR / f"{name}.pdf", llm, profile, dt.date.today()
            )
            write_snapshot(export_snapshot(session, analysis), DEMO_DIR / f"{name}.json")
            print(f"  US$ {analysis.cost_usd or 0:.2f}, gravado em data/demo/{name}.json")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed")
    reset = commands.add_parser("reset")
    reset.add_argument("--yes", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("analysis_id")
    export.add_argument("name")
    generate = commands.add_parser("generate")
    generate.add_argument("--yes", action="store_true")
    generate.add_argument("--names", nargs="+", default=list(DEMO_SAMPLES))
    args = parser.parse_args()

    configure_logging(get_settings().log_level)
    try:
        if args.command == "seed":
            return cmd_seed()
        if args.command == "reset":
            return cmd_reset(args.yes)
        if args.command == "export":
            return cmd_export(args.analysis_id, args.name)
        return cmd_generate(args.yes, args.names)
    except SnapshotError as exc:
        print(f"Erro: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
