import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Chunk, Document, Page
from app.ingestion import service
from tests.test_extract import FakeOcr

PDF = "application/pdf"


def _upload(client: TestClient, content: bytes, filename: str = "edital.pdf") -> dict[str, object]:
    response = client.post("/documents", files={"file": (filename, content, PDF)})
    assert response.status_code in (200, 202), response.text
    body: dict[str, object] = response.json()
    return body


def test_upload_processes_a_long_edital_end_to_end(
    client: TestClient, florianopolis_pdf: bytes
) -> None:
    response = client.post(
        "/documents", files={"file": ("CC 90330-2026.pdf", florianopolis_pdf, PDF)}
    )

    assert response.status_code == 202
    uploaded = response.json()
    assert uploaded["duplicate"] is False
    assert uploaded["source"] == "upload"
    assert uploaded["file_hash"] == hashlib.sha256(florianopolis_pdf).hexdigest()

    # TestClient runs background tasks before returning, so processing is done.
    detail = client.get(f"/documents/{uploaded['id']}").json()
    assert detail["status"] == "ready"
    assert detail["error"] is None
    assert detail["page_count"] == 88
    assert detail["chunk_count"] > 100
    assert [page["number"] for page in detail["pages"]] == list(range(1, 89))
    assert not any(page["ocr"] for page in detail["pages"])
    assert detail["metadata"]["ocr_pages"] == []
    assert detail["metadata"]["warnings"] == []

    page = client.get(f"/documents/{uploaded['id']}/pages/2").json()
    assert page["number"] == 2
    assert "R$ 22.549.875,04" in page["text"]

    chunks = client.get(f"/documents/{uploaded['id']}/chunks").json()
    assert len(chunks) == detail["chunk_count"]
    contract = next(c for c in chunks if c["heading"] == "ANEXO II – MINUTA DO CONTRATO")
    assert (contract["kind"], contract["page_start"]) == ("annex", 64)


def test_same_file_uploaded_twice_is_stored_once(
    client: TestClient, db_engine: Engine, lauro_muller_pdf: bytes
) -> None:
    first = _upload(client, lauro_muller_pdf, "edital.pdf")
    response = client.post("/documents", files={"file": ("outro nome.pdf", lauro_muller_pdf, PDF)})

    assert response.status_code == 200
    second = response.json()
    assert second["duplicate"] is True
    assert second["id"] == first["id"]
    assert second["filename"] == "edital.pdf"  # the original record is returned as is
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(Page)) == 28
    stored = list(get_settings().storage_dir.iterdir())
    assert [path.name for path in stored] == [f"{first['file_hash']}.pdf"]


def test_scanned_pages_go_through_ocr_and_are_flagged(
    client: TestClient, mixed_scan_pdf: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "default_ocr_engine", lambda: FakeOcr())

    uploaded = _upload(client, mixed_scan_pdf)
    detail = client.get(f"/documents/{uploaded['id']}").json()

    assert detail["status"] == "ready"
    assert [page["ocr"] for page in detail["pages"]] == [False, True, False]
    assert detail["metadata"]["ocr_pages"] == [2]
    page = client.get(f"/documents/{uploaded['id']}/pages/2").json()
    assert page == {"number": 2, "ocr": True, "text": "texto reconhecido da página 2"}


def test_scanned_pages_without_ocr_are_reported_as_a_warning(
    client: TestClient, mixed_scan_pdf: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "default_ocr_engine", lambda: FakeOcr(available=False))

    uploaded = _upload(client, mixed_scan_pdf)
    detail = client.get(f"/documents/{uploaded['id']}").json()

    assert detail["status"] == "ready"
    assert detail["pages"][1] == {"number": 2, "ocr": False, "char_count": 0}
    assert len(detail["metadata"]["warnings"]) == 1


def test_corrupted_pdf_is_marked_failed_and_can_be_retried(
    client: TestClient, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = b"%PDF-1.7\nthis is not really a pdf"

    uploaded = _upload(client, broken)
    detail = client.get(f"/documents/{uploaded['id']}").json()

    assert detail["status"] == "failed"
    assert detail["error"] == "O arquivo não é um PDF legível."
    assert detail["pages"] == []

    # Uploading it again triggers a new attempt instead of returning the stale failure.
    attempts: list[uuid.UUID] = []
    monkeypatch.setattr("app.api.documents.process_document", attempts.append)
    again = client.post("/documents", files={"file": ("edital.pdf", broken, PDF)})
    assert again.status_code == 200
    assert attempts == [uuid.UUID(str(uploaded["id"]))]


def test_reprocessing_replaces_previous_pages_and_chunks(
    client: TestClient, db_engine: Engine, lauro_muller_pdf: bytes
) -> None:
    uploaded = _upload(client, lauro_muller_pdf)
    document_id = uuid.UUID(str(uploaded["id"]))

    service.process_document(document_id)

    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Page)) == 28
        chunk_indexes = session.scalars(select(Chunk.index).order_by(Chunk.index)).all()
        assert list(chunk_indexes) == list(range(len(chunk_indexes)))


def test_non_pdf_upload_is_rejected(client: TestClient, db_engine: Engine) -> None:
    response = client.post(
        "/documents", files={"file": ("edital.pdf", b"PK\x03\x04 a zip renamed to pdf", PDF)}
    )

    assert response.status_code == 415
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0
    assert not get_settings().storage_dir.exists()


def test_empty_upload_is_rejected(client: TestClient) -> None:
    response = client.post("/documents", files={"file": ("edital.pdf", b"", PDF)})

    assert response.status_code == 400


def test_upload_above_the_size_limit_is_rejected(
    client: TestClient, lauro_muller_pdf: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)

    response = client.post("/documents", files={"file": ("edital.pdf", lauro_muller_pdf, PDF)})

    assert response.status_code == 413


def test_client_filename_is_never_used_as_a_path(
    client: TestClient, lauro_muller_pdf: bytes, tmp_path: Path
) -> None:
    uploaded = _upload(client, lauro_muller_pdf, "../../../evil.pdf")

    storage = get_settings().storage_dir
    assert [path.name for path in storage.iterdir()] == [f"{uploaded['file_hash']}.pdf"]
    assert not (tmp_path / "evil.pdf").exists()
    assert not list(tmp_path.parent.glob("evil.pdf"))


def test_unknown_document_and_page_return_404(client: TestClient, lauro_muller_pdf: bytes) -> None:
    missing = uuid.uuid4()
    assert client.get(f"/documents/{missing}").status_code == 404
    assert client.get(f"/documents/{missing}/chunks").status_code == 404
    assert client.get(f"/documents/{missing}/pages/1").status_code == 404
    assert client.get("/documents/not-a-uuid").status_code == 422

    uploaded = _upload(client, lauro_muller_pdf)
    assert client.get(f"/documents/{uploaded['id']}/pages/29").status_code == 404
