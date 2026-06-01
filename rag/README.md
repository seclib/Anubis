# RAG

The RAG layer exposes retrieval and indexing over Markdown knowledge.

## Entry Points

- Desktop RAG API: `backend.rag.indexer.RagIndexer`
- Desktop retrieval API: `backend.rag.retriever.RagRetriever`
- Legacy hybrid facade: `rag.service.RAGService`

## Interface

- Index Markdown from the vault into Qdrant.
- Search Qdrant for chunks.
- Treat Markdown as source of truth; vector stores are rebuildable caches.

## Coupling Rule

RAG may read through vault services and write to vector stores. It should not
call UI, launcher, or concrete agent loops.
