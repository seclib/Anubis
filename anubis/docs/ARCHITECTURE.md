# Anubis Architecture

Anubis is split into independently runnable applications and packages.

## Desktop

The Tauri app owns system bridging only. It sends HTTP requests to AI Core through async Rust commands and renders the workspace with React.

## AI Core

AI Core is the orchestration boundary. It validates user input, builds prompts, calls an injected LLM client, retrieves context from RAG, executes tools through a registry, and returns structured responses.

## RAG

The RAG service owns ingestion, chunking, embeddings, and vector search. Qdrant is the long-term memory store. The service exposes `/ingest`, `/search`, and `/query`.

## Tools

Tools are independent modules with JSON schemas, async executors, validation, timeouts, and structured execution logs.

## Memory

Short-term memory is process-local by default and can be swapped for Redis. Long-term memory is stored in Qdrant through the RAG service. Structured memory is stored as JSON documents by `memory-sdk`.
