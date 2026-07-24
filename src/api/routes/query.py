"""Query endpoint: hybrid retrieval (no generation yet)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.api.deps import get_retriever
from src.api.rate_limit import limiter
from src.rag.retrievers.protocol import Retriever
from src.rag.retrievers.routing import get_last_routing_info
from src.types import Query, RetrievalResponse

router = APIRouter()


# Retrieval runs bge-m3 on CPU, so /query is the one unauthenticated endpoint
# that can hold the single instance (maxScale=1) busy and bill for it. The
# `request: Request` parameter is what slowapi keys the per-IP limit on.
@router.post("/query", response_model=RetrievalResponse)
@limiter.limit("10/minute")
async def query(
    request: Request, payload: Query, retriever: Retriever = Depends(get_retriever)
) -> RetrievalResponse:
    results = await retriever.retrieve(payload)
    # When the retriever is a RoutingRetriever, it has populated the contextvar
    # with its decision; PipelineRetriever wired directly leaves it at None.
    return RetrievalResponse(results=results, routing=get_last_routing_info())
