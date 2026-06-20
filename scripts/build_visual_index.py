"""Build the persisted ColQwen2 page index into a Qdrant multivector collection.

Run once, offline, on a machine with a GPU (ADR 0028). It renders every PDF
page, embeds each page with ColQwen2, and upserts the page multivectors into
``--collection`` inside the same embedded Qdrant store the text corpus lives in.
The deploy then loads these vectors at startup instead of re-encoding pages,
which is what makes the visual leg viable on a CPU-only Cloud Run box.

Encoding reuses ``build_visual_retriever`` — the exact path the offline eval
scores — so the persisted vectors are identical to the eval's in-memory ones.
That is what lets the deployed router reproduce the eval's recall number.

Memory: this loads every page embedding into memory at once (same profile as
the in-memory eval leg). Run it on the GPU box with no other GPU work in flight
(the 8 GB card OOMs if Ollama or a desktop compositor is holding VRAM).

Usage:

    .venv/Scripts/python.exe -m scripts.build_visual_index \\
        --pdf-dir data/papers \\
        --qdrant path:./qdrant_local \\
        --collection rag_corpus_visual \\
        --pages-dir data/pages

Idempotent: refuses to rebuild a non-empty collection unless ``--force``
(which drops only the visual collection, leaving the text collection intact).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import torch

from src.observability.logging import configure_logging, get_logger
from src.rag.retrievers.visual import build_visual_retriever
from src.rag.visual_store import QdrantVisualStore

_UPSERT_BATCH = 32


async def _main(
    *,
    pdf_dir: Path,
    pdfs: list[Path] | None,
    qdrant_url: str,
    collection: str,
    corpus_collection: str,
    pages_dir: Path,
    visual_model: str,
    device: str,
    dpi: int,
    force: bool,
) -> None:
    log = get_logger("scripts.build_visual_index")
    pdf_paths = sorted(pdfs) if pdfs else sorted(pdf_dir.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(f"No .pdf files found in {pdf_dir}")

    # Scope to the served text corpus: the visual index must cover exactly the
    # papers `corpus_collection` holds. Globbing data/papers otherwise pulls in
    # the ingestion-robustness fixtures (het-apollo17's 339 pages, het-*-slides,
    # het-hal-fr) that are not served — they would bloat the baked index and
    # surface visual pages with no text counterpart. Read + close before the
    # encode so the embedded path-mode lock is free for the upsert step (local
    # mode rejects two live clients on one path).
    from src.rag.vectorstore import QdrantVectorStore

    text_store = QdrantVectorStore(url=qdrant_url, collection_name=corpus_collection, dim=1024)
    try:
        corpus_papers = {c.paper_id for c in await text_store.scroll_chunks()}
    finally:
        await text_store._client.close()
    if corpus_papers:
        skipped = sorted(p.stem for p in pdf_paths if p.stem not in corpus_papers)
        pdf_paths = [p for p in pdf_paths if p.stem in corpus_papers]
        if skipped:
            print(
                f"Skipping {len(skipped)} PDFs not in {corpus_collection!r}: {', '.join(skipped)}"
            )
    else:
        print(f"WARNING: {corpus_collection!r} is empty — encoding all globbed PDFs unscoped")
    if not pdf_paths:
        raise SystemExit(f"No PDFs left after scoping to {corpus_collection!r}.")
    print(f"Encoding {len(pdf_paths)} papers (scoped to {corpus_collection!r})")

    # Idempotency / --force, then close so the encode + upsert can reopen.
    store = QdrantVisualStore(url=qdrant_url, collection_name=collection)
    try:
        existing = await store.count()
        if existing > 0 and not force:
            print(
                f"Collection {collection!r} already has {existing} pages — skipping (--force to rebuild)."
            )
            log.info("build_visual.skip", collection=collection, existing=existing)
            return
        if existing > 0 and force:
            print(f"--force: dropping {existing} pages in {collection!r}")
            await store.delete_collection()
    finally:
        await store.close()

    # Render every page to PNG (idempotent), then encode via the same path the
    # eval uses so the persisted vectors match it.
    from src.ingestion.visual import render_pages

    pages_by_paper: dict[str, list[tuple[int, Path]]] = {}
    for pdf_path in pdf_paths:
        paper_id = pdf_path.stem
        rendered = render_pages(paper_id, pdf_path, out_dir=pages_dir, dpi=dpi)
        pages_by_paper[paper_id] = [(r.page_number, r.image_path) for r in rendered]
        print(f"  {paper_id}: {len(rendered)} pages")

    print(f"Embedding pages with {visual_model} on {device} (the slow part)...")
    retriever = await build_visual_retriever(pages_by_paper, model_name=visual_model, device=device)
    page_embeds = retriever._page_embeds  # chunk_id -> [n_patches, dim] tensor
    page_meta = retriever._page_meta  # chunk_id -> (paper_id, page_no)
    if not page_embeds:
        raise SystemExit("No pages embedded — nothing to persist.")

    dim = int(next(iter(page_embeds.values())).shape[-1])
    pages: list[tuple[str, int, list[list[float]]]] = []
    for chunk_id, embed in page_embeds.items():
        paper_id, page_no = page_meta[chunk_id]
        pages.append((paper_id, page_no, embed.float().cpu().tolist()))

    out_store = QdrantVisualStore(url=qdrant_url, collection_name=collection, dim=dim)
    try:
        await out_store.ensure_collection()
        for start in range(0, len(pages), _UPSERT_BATCH):
            await out_store.upsert_pages(pages[start : start + _UPSERT_BATCH])
        final = await out_store.count()
        print(f"\nPersisted {final} page vectors (dim={dim}) into {collection!r}")
        log.info(
            "build_visual.done",
            collection=collection,
            papers=len(pdf_paths),
            pages=final,
            dim=dim,
            model=visual_model,
        )
    finally:
        await out_store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Render + embed PDF pages into a Qdrant multivector collection."
    )
    parser.add_argument("--pdf-dir", type=Path, default=Path("data/papers"))
    parser.add_argument(
        "--pdf",
        dest="pdfs",
        type=Path,
        action="append",
        help="Embed specific PDF file(s) instead of globbing --pdf-dir (repeatable).",
    )
    parser.add_argument("--qdrant", default="path:./qdrant_local")
    parser.add_argument("--collection", default="rag_corpus_visual")
    parser.add_argument(
        "--corpus-collection",
        default="rag_corpus",
        help="Text collection to scope the visual index to (encode only its papers).",
    )
    parser.add_argument("--pages-dir", type=Path, default=Path("data/pages"))
    parser.add_argument("--visual-model", default="vidore/colqwen2-v1.0")
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="Torch device for embedding. Defaults to cuda when available.",
    )
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if the collection is non-empty (drops only this collection).",
    )
    args = parser.parse_args()

    configure_logging(level="INFO", env="local", log_file=None)
    asyncio.run(
        _main(
            pdf_dir=args.pdf_dir,
            pdfs=args.pdfs,
            qdrant_url=args.qdrant,
            collection=args.collection,
            corpus_collection=args.corpus_collection,
            pages_dir=args.pages_dir,
            visual_model=args.visual_model,
            device=args.device,
            dpi=args.dpi,
            force=args.force,
        )
    )
