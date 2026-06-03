"""Task-driven context engine contracts."""

from anubis.context.builder import ContextBuilder
from anubis.context.chunker import CodeChunker
from anubis.context.compressor.compressor import ContextCompressor as AdvancedContextCompressor
from anubis.context.embeddings import EmbeddingCache, EmbeddingProvider, HashEmbeddingProvider
from anubis.context.indexer.indexer import RepositoryIndexer
from anubis.context.interfaces import (
    ContextCompressor,
    ContextEngine,
    ContextIndexer,
    ContextRetriever,
)
from anubis.context.retriever.retriever import HybridContextRetriever
from anubis.context.scanner import RepositoryScanner
from anubis.context.schema import BuiltContext, CodeChunk, FileMetadata, RepositoryIndex, RetrievedContext

__all__ = [
    "AdvancedContextCompressor",
    "BuiltContext",
    "CodeChunk",
    "CodeChunker",
    "ContextBuilder",
    "ContextCompressor",
    "ContextEngine",
    "ContextIndexer",
    "ContextRetriever",
    "EmbeddingCache",
    "EmbeddingProvider",
    "FileMetadata",
    "HashEmbeddingProvider",
    "HybridContextRetriever",
    "RepositoryIndex",
    "RepositoryIndexer",
    "RepositoryScanner",
    "RetrievedContext",
]
