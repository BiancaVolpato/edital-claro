"""Snapshots of finished analyses, used to seed the public demo.

A snapshot is a JSON file in data/demo/ holding one analysis exactly as the real
pipeline produced it (fields, citations, risks, per-call usage and audit trail),
plus the eligibility checks made on it. The PDF itself is not copied: the
snapshot names a file in data/samples/ and its SHA-256, and seeding runs the
normal ingestion on it, so pages and chunks are rebuilt by the same code.

Seeding never calls the LLM nor loads the embedding model. See ADR-039.
"""

import datetime as dt
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Analysis,
    AnalysisStatus,
    Chunk,
    CompanyProfile,
    Document,
    DocumentSource,
    DocumentStatus,
    EligibilityCheck,
    Page,
)
from app.eligibility.profile import CompanyProfileData
from app.eligibility.records import record_eligibility_check
from app.extraction.service import create_analysis, process_analysis
from app.ingestion.service import process_document, register_document
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "data" / "demo"
SAMPLES_DIR = REPO_ROOT / "data" / "samples"
EXAMPLE_PROFILE_FILE = REPO_ROOT / "data" / "profiles" / "construtora_exemplo.json"
# The editais of the public demo: native text (no OCR) and different kinds of works.
DEMO_SAMPLES = (
    "lauro_muller_cc_233_2026",
    "palhoca_cce_241_2026",
    "witmarsum_cce_4_2026",
)

# Columns copied as they are; ids, foreign keys and the document link are rebuilt.
ANALYSIS_FIELDS = (
    "status",
    "error",
    "steps_done",
    "steps_total",
    "strategy",
    "prompt_version",
    "prompt_hash",
    "llm_provider",
    "llm_model",
    "embedding_model",
    "risk_prompt_version",
    "risk_prompt_hash",
    "cost_limit_usd",
    "app_version",
    "result",
    "risks",
    "runs",
    "citation_counts",
    "warnings",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "latency_ms",
)
ELIGIBILITY_FIELDS = (
    "profile_snapshot",
    "report",
    "prompt_version",
    "prompt_hash",
    "llm_model",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "cost_limit_usd",
    "app_version",
)


class SnapshotError(Exception):
    """A snapshot cannot be exported or loaded (message in Portuguese, for the CLI)."""


@dataclass
class SeedResult:
    loaded: list[str]
    skipped: list[str]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_sample(file_hash: str, samples_dir: Path = SAMPLES_DIR) -> Path:
    for path in sorted(samples_dir.glob("*.pdf")):
        if sha256_of(path) == file_hash:
            return path
    raise SnapshotError(
        f"O PDF desta análise não está em {samples_dir}. Copie o arquivo para lá antes de "
        "exportar: a demonstração precisa dele para mostrar as citações."
    )


def export_snapshot(
    session: Session, analysis: Analysis, samples_dir: Path = SAMPLES_DIR
) -> dict[str, Any]:
    """The analysis (completed) and its eligibility checks as a JSON-ready dict."""
    if analysis.status != AnalysisStatus.COMPLETED.value or analysis.result is None:
        raise SnapshotError(f"A análise {analysis.id} não está concluída ({analysis.status}).")
    document = analysis.document
    pdf = find_sample(document.file_hash, samples_dir)
    checks = session.scalars(
        select(EligibilityCheck)
        .where(EligibilityCheck.analysis_id == analysis.id)
        .order_by(EligibilityCheck.created_at)
    ).all()
    try:
        pdf_ref = pdf.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pdf_ref = pdf.as_posix()
    return {
        "format": FORMAT_VERSION,
        "pdf": pdf_ref,
        "file_sha256": document.file_hash,
        "document": {
            "filename": document.filename,
            "source": document.source,
            "source_ref": document.source_ref,
            "pncp": (document.meta or {}).get("pncp"),
        },
        "analysis": {
            **{field: getattr(analysis, field) for field in ANALYSIS_FIELDS},
            "created_at": _iso(analysis.created_at),
            "completed_at": _iso(analysis.completed_at),
        },
        "eligibility": [
            {
                **{field: getattr(check, field) for field in ELIGIBILITY_FIELDS},
                "created_at": _iso(check.created_at),
            }
            for check in checks
        ],
    }


def write_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_snapshots(demo_dir: Path = DEMO_DIR) -> list[tuple[str, dict[str, Any]]]:
    snapshots = []
    for path in sorted(demo_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != FORMAT_VERSION:
            raise SnapshotError(f"{path.name}: formato {data.get('format')} não suportado.")
        snapshots.append((path.stem, data))
    return snapshots


def _pdf_path(snapshot: dict[str, Any]) -> Path:
    path = Path(snapshot["pdf"])
    return path if path.is_absolute() else REPO_ROOT / path


def _profile_for(session: Session, data: dict[str, Any]) -> CompanyProfile:
    """The profile with exactly this content, created if missing."""
    for profile in session.scalars(select(CompanyProfile)):
        if profile.data == data:
            return profile
    profile = CompanyProfile(name=data["name"], data=data)
    session.add(profile)
    session.flush()
    return profile


def load_snapshot(session: Session, name: str, snapshot: dict[str, Any]) -> bool:
    """Store one snapshot. False when its document already has a completed analysis."""
    pdf = _pdf_path(snapshot)
    if not pdf.exists():
        raise SnapshotError(f"{name}: arquivo {snapshot['pdf']} não encontrado.")
    content = pdf.read_bytes()
    if hashlib.sha256(content).hexdigest() != snapshot["file_sha256"]:
        raise SnapshotError(f"{name}: {snapshot['pdf']} mudou desde que o snapshot foi gerado.")

    info = snapshot["document"]
    registered = register_document(
        session,
        content,
        info["filename"],
        DocumentSource(info["source"]),
        info.get("source_ref"),
    )
    document = registered.document
    if registered.created and info.get("pncp"):
        document.meta = {**(document.meta or {}), "pncp": info["pncp"]}
        session.commit()
    if document.status != DocumentStatus.READY.value:
        process_document(document.id)
        session.refresh(document)
        if document.status != DocumentStatus.READY.value:
            raise SnapshotError(f"{name}: falha ao processar o PDF ({document.error}).")

    already = session.scalar(
        select(Analysis.id).where(
            Analysis.document_id == document.id,
            Analysis.status == AnalysisStatus.COMPLETED.value,
        )
    )
    if already is not None:
        return False

    stored = snapshot["analysis"]
    analysis = Analysis(
        document_id=document.id,
        **{field: stored[field] for field in ANALYSIS_FIELDS},
        created_at=_parse(stored["created_at"]),
        completed_at=_parse(stored["completed_at"]),
    )
    session.add(analysis)
    session.flush()
    for check in snapshot["eligibility"]:
        profile = _profile_for(session, check["profile_snapshot"])
        session.add(
            EligibilityCheck(
                analysis_id=analysis.id,
                profile_id=profile.id,
                **{field: check[field] for field in ELIGIBILITY_FIELDS},
                created_at=_parse(check["created_at"]),
            )
        )
    session.commit()
    logger.info("demo snapshot loaded", extra={"snapshot": name, "analysis_id": str(analysis.id)})
    return True


def seed(session: Session, demo_dir: Path = DEMO_DIR) -> SeedResult:
    """Load every snapshot in ``demo_dir``; safe to run on every start."""
    result = SeedResult(loaded=[], skipped=[])
    for name, snapshot in read_snapshots(demo_dir):
        (result.loaded if load_snapshot(session, name, snapshot) else result.skipped).append(name)
    return result


def clear_data(session: Session) -> dict[str, int]:
    """Delete documents, analyses, profiles and eligibility checks, and the stored PDFs.

    The law index is kept: it is reference data, rebuilt by its own script.
    """
    counts = {}
    for model in (EligibilityCheck, Analysis, Chunk, Page, Document, CompanyProfile):
        counts[model.__tablename__] = session.execute(delete(model)).rowcount  # type: ignore[attr-defined]
    session.commit()
    storage = get_settings().storage_dir
    removed = 0
    if storage.exists():
        for path in storage.glob("*.pdf"):
            path.unlink()
            removed += 1
    counts["arquivos"] = removed
    return counts


def example_profile(session: Session) -> CompanyProfile:
    """The example bidder of data/profiles, stored once."""
    data = json.loads(EXAMPLE_PROFILE_FILE.read_text(encoding="utf-8"))
    return _profile_for(session, CompanyProfileData.model_validate(data).model_dump(mode="json"))


def analyze_sample(
    session: Session,
    pdf: Path,
    llm: LLMProvider,
    profile: CompanyProfile,
    today: dt.date,
) -> Analysis:
    """Run the real pipeline on a sample and an eligibility check with ``profile``.

    Used to (re)generate the demo snapshots. Calls the LLM: costs money.
    """
    registered = register_document(session, pdf.read_bytes(), pdf.name, DocumentSource.UPLOAD)
    document = registered.document
    if document.status != DocumentStatus.READY.value:
        process_document(document.id)
        session.refresh(document)
        if document.status != DocumentStatus.READY.value:
            raise SnapshotError(f"{pdf.name}: falha ao processar o PDF ({document.error}).")
    analysis = create_analysis(session, document, llm)
    process_analysis(analysis.id, llm)
    session.refresh(analysis)
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise SnapshotError(f"{pdf.name}: a análise falhou ({analysis.error}).")
    record_eligibility_check(session, analysis, profile, llm, today)
    return analysis
