"""``spectrarag`` command-line entry point.

A thin convenience layer over the documented workflows: one command instead of
a chain of ``python -m scripts.*``. ``serve`` runs the API self-contained
(in-process bge-m3 + the committed embedded Qdrant snapshot, no Docker or Ollama
needed); ``ingest`` and ``fetch`` wrap the existing scripts.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable


def _run_module(module: str, args: list[str]) -> int:
    """Run ``python -m <module> <args>`` in a subprocess; return its exit code."""
    return subprocess.run([sys.executable, "-m", module, *args], check=False).returncode


def _serve(ns: argparse.Namespace) -> int:
    # Self-contained defaults so `spectrarag serve` works after a clone with no
    # external services: in-process sentence-transformers bge-m3 (no Ollama) and
    # the committed embedded Qdrant snapshot (no Qdrant server). setdefault only
    # fills these when the user hasn't set them via the shell or .env.
    os.environ.setdefault("RAG_EMBEDDER_BACKEND", "sentence_transformers")
    os.environ.setdefault("RAG_QDRANT_URL", "path:./qdrant_local")
    # bge-reranker-v2-m3 (the default) reranks the candidate pool in minutes per
    # query on CPU; the small MiniLM cross-encoder the Cloud Run image uses is
    # CPU-feasible and non-inferior on the eval sets (ADR 0012).
    os.environ.setdefault("RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    if os.path.isdir("data/pages"):
        os.environ.setdefault("RAG_PAGES_DIR", "data/pages")

    import uvicorn

    uvicorn.run("src.api.main:app", host=ns.host, port=ns.port, reload=ns.reload)
    return 0


def _ingest(ns: argparse.Namespace) -> int:
    args = ["--pdf-dir", ns.pdf_dir, "--collection", ns.collection]
    if ns.force:
        args.append("--force")
    return _run_module("scripts.bootstrap_corpus", args)


def _fetch(ns: argparse.Namespace) -> int:
    args = ["--out-dir", ns.out_dir]
    if ns.manifest:
        args += ["--manifest", ns.manifest]
    return _run_module("scripts.fetch_papers", args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spectrarag",
        description="Multi-modal PDF RAG: serve the API, ingest PDFs, or fetch the demo corpus.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser(
        "serve", help="Run the API self-contained (in-process bge-m3 + embedded Qdrant)."
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev).")
    serve.set_defaults(func=_serve)

    ingest = sub.add_parser(
        "ingest", help="Ingest a folder of PDFs into a collection (needs Ollama for bge-m3)."
    )
    ingest.add_argument("--pdf-dir", default="data/papers")
    ingest.add_argument("--collection", default="rag_corpus")
    ingest.add_argument(
        "--force", action="store_true", help="Re-ingest into a non-empty collection."
    )
    ingest.set_defaults(func=_ingest)

    fetch = sub.add_parser("fetch", help="Download demo-corpus PDFs from a manifest of arXiv IDs.")
    fetch.add_argument("--manifest", default="data/curated_demo/papers.txt")
    fetch.add_argument("--out-dir", default="data/papers")
    fetch.set_defaults(func=_fetch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] = ns.func
    return func(ns)


if __name__ == "__main__":
    raise SystemExit(main())
