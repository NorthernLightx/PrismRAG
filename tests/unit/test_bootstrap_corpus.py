"""bootstrap_corpus batch resilience: one bad PDF skips, the rest still ingest."""

from pathlib import Path

from scripts.bootstrap_corpus import _ingest_each


async def test_ingest_each_skips_bad_pdf_and_continues() -> None:
    paths = [Path("a.pdf"), Path("b.pdf"), Path("c.pdf")]

    async def ingest_one(pdf_path: Path) -> int:
        if pdf_path.name == "b.pdf":
            raise ValueError("corrupt PDF")
        return 5

    total, skipped = await _ingest_each(paths, ingest_one)

    assert total == 10  # a.pdf + c.pdf ingested; b.pdf skipped
    assert skipped == ["b.pdf"]


async def test_ingest_each_all_good() -> None:
    paths = [Path("a.pdf"), Path("b.pdf")]

    async def ingest_one(pdf_path: Path) -> int:
        return 3

    total, skipped = await _ingest_each(paths, ingest_one)

    assert total == 6
    assert skipped == []
