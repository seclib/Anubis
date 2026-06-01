from __future__ import annotations

from fastapi import Request

from anubis_rag.core.config import Settings
from anubis_rag.ingestion.chunker import MarkdownChunker
from anubis_rag.ingestion.embedder import HashEmbeddingModel
from anubis_rag.storage.qdrant_store import QdrantVectorStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_vector_store(request: Request) -> QdrantVectorStore:
    return request.app.state.vector_store


def get_chunker(request: Request) -> MarkdownChunker:
    settings = get_settings(request)
    return MarkdownChunker(settings.chunk_size, settings.chunk_overlap)


def get_embedder(request: Request) -> HashEmbeddingModel:
    settings = get_settings(request)
    return HashEmbeddingModel(settings.embedding_dimensions)
