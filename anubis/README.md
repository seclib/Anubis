# Anubis

Local-first desktop AI workspace with chat, retrieval-augmented memory, and a modular tool system.

## Architecture

- `apps/desktop`: Tauri + React + TypeScript desktop application.
- `services/ai-core`: FastAPI orchestration service for chat, tools, prompts, and conversation state.
- `services/rag`: FastAPI retrieval service backed by Qdrant.
- `services/tools`: Python plugin-style tool registry and built-in tools.
- `packages/shared-types`: TypeScript contracts shared by UI clients.
- `packages/prompt-engine`: Prompt composition package.
- `packages/memory-sdk`: Short-term and structured memory helpers.
- `infra/docker/qdrant`: Local Qdrant compose file.
- `infra/configs`: Environment templates and service configuration.

## Quick Start

```bash
cd anubis
docker compose -f infra/docker/qdrant/docker-compose.yml up -d

cd services/rag
python -m venv .venv
. .venv/bin/activate
pip install -e .
uvicorn anubis_rag.main:create_app --factory --reload --port 8101

cd ../../services/ai-core
python -m venv .venv
. .venv/bin/activate
pip install -e . ../../packages/prompt-engine ../../packages/memory-sdk ../tools
uvicorn anubis_ai_core.main:create_app --factory --reload --port 8100

cd ../../apps/desktop
npm install
npm run tauri dev
```

## Runtime Defaults

- AI Core: `http://127.0.0.1:8100`
- RAG Service: `http://127.0.0.1:8101`
- Qdrant: `http://127.0.0.1:6333`

No absolute user-specific paths are required. Runtime directories are configured with environment variables or defaults relative to the current working directory.

See `docs/COMMUNICATION.md` for concrete desktop, AI Core, RAG, and tool registry calls.

See `docs/ANUBIS_OS_ARCHITECTURE.md` for the full production OS architecture and runtime ownership map.
