"""spectrarag CLI: dispatch + self-contained serve defaults."""

import os
from unittest import mock

import pytest

from src.cli import main


def test_serve_sets_self_contained_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("RAG_EMBEDDER_BACKEND", "RAG_QDRANT_URL", "RAG_PAGES_DIR"):
        monkeypatch.delenv(var, raising=False)
    with mock.patch("uvicorn.run") as run:
        rc = main(["serve", "--port", "9000"])
    assert rc == 0
    run.assert_called_once()
    assert run.call_args.args[0] == "src.api.main:app"
    assert run.call_args.kwargs["port"] == 9000
    assert os.environ["RAG_EMBEDDER_BACKEND"] == "sentence_transformers"
    assert os.environ["RAG_QDRANT_URL"] == "path:./qdrant_local"


def test_serve_respects_user_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_EMBEDDER_BACKEND", "ollama")
    with mock.patch("uvicorn.run"):
        main(["serve"])
    assert os.environ["RAG_EMBEDDER_BACKEND"] == "ollama"


def test_fetch_invokes_fetch_papers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, list[str]]] = []

    def fake_run(module: str, args: list[str]) -> int:
        captured.append((module, args))
        return 0

    monkeypatch.setattr("src.cli._run_module", fake_run)
    rc = main(["fetch", "--manifest", "m.txt"])
    assert rc == 0
    assert len(captured) == 1
    module, args = captured[0]
    assert module == "scripts.fetch_papers"
    assert "--manifest" in args
    assert "m.txt" in args


def test_no_subcommand_errors() -> None:
    with pytest.raises(SystemExit):
        main([])
