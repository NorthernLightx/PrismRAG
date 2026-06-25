"""POST /ingest (ADR 0029): flag gate, validation, and the happy-path append."""

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_settings
from src.api.main import create_app
from src.config.settings import Settings


def _app(enable_upload: bool) -> TestClient:
    app = create_app(log_file=None)
    app.dependency_overrides[get_settings] = lambda: Settings(enable_upload=enable_upload)
    return TestClient(app)


def test_ingest_disabled_returns_403() -> None:
    resp = _app(enable_upload=False).post(
        "/ingest", files={"file": ("d.pdf", b"%PDF-1.4 x", "application/pdf")}
    )
    assert resp.status_code == 403


def test_ingest_rejects_non_pdf() -> None:
    resp = _app(enable_upload=True).post(
        "/ingest", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert resp.status_code == 400


def test_ingest_rejects_empty_upload() -> None:
    resp = _app(enable_upload=True).post(
        "/ingest", files={"file": ("x.pdf", b"", "application/pdf")}
    )
    assert resp.status_code == 400


def test_ingest_happy_path_appends_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _app(enable_upload=True)
    chunks: dict[str, object] = {}
    added = [mock.Mock(chunk_id="mydoc::p1::c0"), mock.Mock(chunk_id="mydoc::p1::c1")]

    async def fake_ingest(**kwargs: object) -> mock.Mock:
        return mock.Mock(chunk_count=len(added), chunks=added)

    monkeypatch.setattr(
        "src.api.routes.ingest.get_corpus_handles",
        lambda: (mock.Mock(), mock.Mock(), mock.Mock()),
    )
    monkeypatch.setattr("src.api.routes.ingest.get_chunks", lambda: chunks)
    monkeypatch.setattr("src.api.routes.ingest.ingest_paper", fake_ingest)

    resp = client.post("/ingest", files={"file": ("mydoc.pdf", b"%PDF stub", "application/pdf")})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["paper_id"] == "mydoc"
    assert body["chunks_added"] == 2
    assert len(chunks) == 2


def test_ingest_parse_failure_returns_generic_message(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _app(enable_upload=True)

    async def fake_ingest(**kwargs: object) -> mock.Mock:
        raise ValueError("internal detail C:/secret/path")

    monkeypatch.setattr(
        "src.api.routes.ingest.get_corpus_handles",
        lambda: (mock.Mock(), mock.Mock(), mock.Mock()),
    )
    monkeypatch.setattr("src.api.routes.ingest.get_chunks", lambda: {})
    monkeypatch.setattr("src.api.routes.ingest.ingest_paper", fake_ingest)

    resp = client.post("/ingest", files={"file": ("x.pdf", b"%PDF bad", "application/pdf")})

    assert resp.status_code == 422
    assert "internal detail" not in resp.text  # no exception/path leakage to the client
    assert "Could not parse" in resp.text
