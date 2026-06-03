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
from anubis.context.service import ContextBuilderService
from anubis.context.schema import (
    BuiltContext,
    CodeChunk,
    ContextBudget,
    ContextBuildRequest,
    FileMetadata,
    MinimalContext,
    RankedFile,
    RepositoryIndex,
    RetrievedContext,
)

__all__ = [
    "AdvancedContextCompressor",
    "BuiltContext",
    "CodeChunk",
    "CodeChunker",
    "ContextBuilder",
    "ContextBuilderService",
    "ContextBudget",
    "ContextBuildRequest",
    "ContextCompressor",
    "ContextEngine",
    "ContextIndexer",
    "ContextRetriever",
    "EmbeddingCache",
    "EmbeddingProvider",
    "FileMetadata",
    "HashEmbeddingProvider",
    "HybridContextRetriever",
    "MinimalContext",
    "RankedFile",
    "RepositoryIndex",
    "RepositoryIndexer",
    "RepositoryScanner",
    "RetrievedContext",
]
