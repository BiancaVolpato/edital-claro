import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.core.middleware import REQUEST_ID_HEADER
from app.db.session import check_database


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("test.logger", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emits_one_json_object_with_core_fields() -> None:
    line = JsonFormatter().format(_record("edital processado"))

    payload = json.loads(line)
    assert "\n" not in line
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["message"] == "edital processado"
    assert payload["timestamp"].endswith("+00:00")


def test_formatter_promotes_extra_fields_and_keeps_accents() -> None:
    line = JsonFormatter().format(_record("ok", document_id=42, orgao="Prefeitura de Itajaí"))

    payload = json.loads(line)
    assert payload["document_id"] == 42
    assert "Itajaí" in line  # not escaped as í


def test_formatter_includes_exception_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())

    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_each_request_is_logged_with_a_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    client.app.dependency_overrides[check_database] = lambda: True  # type: ignore[attr-defined]

    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/health", headers={REQUEST_ID_HEADER: "forged-by-client"})

    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id != "forged-by-client"

    [record] = [r for r in caplog.records if r.name == "app.request"]
    assert record.__dict__["request_id"] == request_id
    assert record.__dict__["path"] == "/health"
    assert record.__dict__["status_code"] == 200
