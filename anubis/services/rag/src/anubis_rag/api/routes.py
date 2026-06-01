from __future__ import annotations

from fastapi import APIRouter, Depends

from anubis_rag.api.dependencies import get_chunker, get_embedder, get_vector_store
from anubis_rag.ingestion.chunker import MarkdownChunker
from anubis_rag.ingestion.embedder import HashEmbeddingModel
from anubis_rag.models.documents import IngestRequest, IngestResponse, SearchRequest, SearchResponse
from anubis_rag.security.models import SafeContextResponse
from anubis_rag.security.pipeline import SecureRagPipeline
from anubis_rag.storage.qdrant_store import QdrantVectorStore

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "rag"}


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    payload: IngestRequest,
    chunker: MarkdownChunker = Depends(get_chunker),
    embedder: HashEmbeddingModel = Depends(get_embedder),
    store: QdrantVectorStore = Depends(get_vector_store),
) -> IngestResponse:
    chunks = [chunk for document in payload.documents for chunk in chunker.chunk(document)]
    vectors = await embedder.embed([chunk.text for chunk in chunks])
    await store.upsert(chunks, vectors)
    return IngestResponse(documents=len(payload.documents), chunks=len(chunks))


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    embedder: HashEmbeddingModel = Depends(get_embedder),
    store: QdrantVectorStore = Depends(get_vector_store),
) -> SearchResponse:
    vector = (await embedder.embed([payload.query]))[0]
    return SearchResponse(results=await store.search(vector, payload.limit))


@router.post("/query", response_model=SearchResponse)
async def query(
    payload: SearchRequest,
    embedder: HashEmbeddingModel = Depends(get_embedder),
    store: QdrantVectorStore = Depends(get_vector_store),
) -> SearchResponse:
    vector = (await embedder.embed([payload.query]))[0]
    return SearchResponse(results=await store.search(vector, payload.limit))


@router.post("/safe-query", response_model=SafeContextResponse)
async def safe_query(
    payload: SearchRequest,
    embedder: HashEmbeddingModel = Depends(get_embedder),
    store: QdrantVectorStore = Depends(get_vector_store),
) -> SafeContextResponse:
    pipeline = SecureRagPipeline()
    sanitized_query = pipeline.sanitize_query(payload.query)
    vector = (await embedder.embed([sanitized_query]))[0]
    chunks = await store.search_chunks(vector, payload.limit)
    return pipeline.build_safe_context(chunks)
