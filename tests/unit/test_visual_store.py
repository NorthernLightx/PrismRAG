"""QdrantVisualStore — multivector round-trip + MaxSim ranking on `:memory:`.

Proves the embedded qdrant-client path: a multivector collection accepts page
multivectors and a 2D query, and ranks by the MAX_SIM comparator. This is the
mechanism the persisted visual leg relies on (ADR 0028).
"""

from __future__ import annotations

from typing import Any

import torch

from src.rag.retrievers.visual import VisualRetriever
from src.rag.visual_store import QdrantVisualStore
from src.types import Query


async def test_upsert_and_search_ranks_planted_page() -> None:
    store = QdrantVisualStore(":memory:", "test_visual", dim=4)
    await store.ensure_collection()
    await store.upsert_pages(
        [
            ("paperA", 1, [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]),
            ("paperB", 2, [[0.0, 1.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]),
        ]
    )
    assert await store.count() == 2

    results = await store.search([[1.0, 0.0, 0.0, 0.0]], top_k=2)
    assert results, "expected at least one hit"
    top = results[0]
    assert top.paper_id == "paperA"
    assert top.chunk_id == "paperA::p1::page"
    assert top.source == "visual"
    assert top.page_numbers == [1]


async def test_paper_filter_restricts_results() -> None:
    store = QdrantVisualStore(":memory:", "test_visual_filter", dim=4)
    await store.ensure_collection()
    await store.upsert_pages(
        [
            ("paperA", 1, [[1.0, 0.0, 0.0, 0.0]]),
            ("paperB", 2, [[1.0, 0.0, 0.0, 0.0]]),
        ]
    )
    results = await store.search([[1.0, 0.0, 0.0, 0.0]], top_k=5, paper_filter="paperB")
    assert results
    assert {r.paper_id for r in results} == {"paperB"}


class _StubBatch:
    """Mimics a transformers BatchEncoding: `.to(device)` + `**batch` unpacking."""

    def to(self, _device: str) -> _StubBatch:
        return self

    def keys(self) -> list[str]:
        return []

    def __getitem__(self, _key: str) -> Any:
        raise KeyError(_key)


class _StubQueryProcessor:
    def process_queries(self, _queries: list[str]) -> _StubBatch:
        return _StubBatch()


class _FixedQueryModel:
    """Returns a fixed `[1, n_q, dim]` query embedding regardless of input, so
    the store-backed retrieve path is exercised with a known query vector."""

    def __init__(self, vec: list[list[float]]) -> None:
        self._t = torch.tensor([vec], dtype=torch.float32)

    def __call__(self, **_kwargs: Any) -> torch.Tensor:
        return self._t


async def test_store_backed_retriever_ranks_aligned_page() -> None:
    """VisualRetriever with a `store` encodes the query and ranks via Qdrant
    MaxSim — the deploy path. The query aligns with paperA's page vector, so
    paperA ranks first."""
    store = QdrantVisualStore(":memory:", "rt_visual", dim=4)
    await store.ensure_collection()
    await store.upsert_pages(
        [
            ("paperA", 1, [[1.0, 0.0, 0.0, 0.0]]),
            ("paperB", 2, [[0.0, 1.0, 0.0, 0.0]]),
        ]
    )
    retriever = VisualRetriever(
        model=_FixedQueryModel([[1.0, 0.0, 0.0, 0.0]]),
        processor=_StubQueryProcessor(),
        store=store,
        device="cpu",
    )

    out = await retriever.retrieve(Query(text="q", top_k=2))

    assert out
    assert out[0].paper_id == "paperA"
    assert out[0].chunk_id == "paperA::p1::page"
    assert out[0].source == "visual"
    assert out[0].page_numbers == [1]
