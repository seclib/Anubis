# Anubis - Systeme autonome local

Anubis est un systeme d'agent IA local, minimal et modulaire, construit autour d'une verite fichier: le vault Obsidian. Le backend expose une API FastAPI, indexe les notes Markdown dans Qdrant, execute une boucle autonome planner/executor/critic, surveille le vault en temps reel et fait evoluer les competences sous forme de fichiers Markdown.

## Changements operes

### API FastAPI de production

Ajout d'une couche API simple dans `backend/api/routes/production.py`, montee dans `backend/main.py`.

Endpoints principaux:

- `POST /ask`: lance la boucle autonome asynchrone.
- `POST /sync`: re-indexe manuellement le vault Obsidian.
- `POST /memory`: recherche du contexte pertinent dans la memoire vectorielle.

Les anciennes routes desktop et RAG restent disponibles.

### Boucle autonome asynchrone

Ajout de `backend/agent/async_loop.py` et `backend/agent/multi_agent.py`.

La boucle suit le flux:

```text
task -> planner -> executor -> critic -> memory update -> result
```

Roles:

- `Planner`: recupere la memoire et decompose la tache.
- `Executor`: execute les etapes et appelle les outils autorises.
- `Critic`: valide le resultat et decide si une relance est necessaire.

Les resultats sont sauvegardes dans `vault/agent-runs/*.md`, puis re-indexes.

### Memoire vectorielle Qdrant

Le pipeline RAG a ete etendu:

- `backend/rag/indexer.py`: ingestion complete ou incrementale.
- `backend/rag/qdrant_store.py`: upsert, recherche semantique et suppression par chemin.
- `backend/rag/chunker.py`: decoupe Markdown.
- `backend/rag/embedder.py`: abstraction d'embedding locale/remplacable.

Qdrant sert de couche de recherche semantique. Le vault Obsidian reste la source de verite.

### Watcher Obsidian temps reel

Ajout et durcissement de `backend/watcher/markdown_watcher.py`.

Fonctions:

- surveillance recursive des fichiers `.md`;
- detection create/update/delete/move;
- debounce pour eviter les doublons;
- ingestion incrementale uniquement;
- fichier d'etat avec hash SHA-256;
- suppression des vecteurs quand une note est supprimee.

Script:

```bash
.venv/bin/python scripts/watch_obsidian.py
```

### Systeme de skills

Ajout de `backend/skills/parser.py` et `backend/skills/engine.py`.

Fonctions:

- lecture des skills Markdown depuis le vault;
- detection de taches repetees;
- extraction de patterns reutilisables;
- generation de nouveaux skills;
- validation par critic avant sauvegarde;
- stockage dans `vault/skills/*.md`;
- re-indexation automatique du skill cree.

Format de skill:

```markdown
# skill: nom_du_skill
tags: [auto-generated, skill]

## trigger
Quand utiliser ce skill.

## procedure
1. Etape reutilisable.
2. Validation.
3. Memoire.
```

### Meta-agent d'amelioration

Ajout de `backend/agent/meta_agent.py`.

Le meta-agent analyse les runs passes et propose des ameliorations pour:

- prompts systeme;
- definitions de skills;
- structure de boucle agentique;
- strategies de recuperation apres erreur.

Il ne modifie pas le systeme directement. Les propositions sont validees par critic puis sauvegardees dans:

```text
vault/meta-agent/proposals/
```

Script:

```bash
.venv/bin/python scripts/run_meta_agent.py
```

### Sandbox d'execution d'outils

Ajout de `backend/tools/sandbox.py`.

Architecture:

```text
ToolRequest -> ToolValidator -> SandboxExecutor -> JSONL Logger
```

Regles:

- commandes whitelistees uniquement;
- execution limitee au dossier projet;
- blocage des operations dangereuses;
- pas de shell control, expansion ou redirection;
- pas de reseau sauf autorisation explicite;
- timeout sur chaque execution;
- journalisation deterministe dans `state/backend_tool_audit.jsonl`.

### Scripts ajoutes

```text
scripts/ingest_obsidian.py      # ingestion manuelle vault -> Qdrant
scripts/run_agent.py            # boucle agent simple
scripts/run_multi_agent.py      # boucle planner/executor/critic
scripts/run_skill_engine.py     # observation + generation de skills
scripts/run_meta_agent.py       # analyse et propositions d'amelioration
scripts/watch_obsidian.py       # watcher temps reel du vault
```

## Structure minimale

```text
backend/
  main.py
  api/routes/
    production.py
  agent/
    async_loop.py
    llm.py
    loop.py
    meta_agent.py
    multi_agent.py
    prompts.py
    tools.py
  rag/
    chunker.py
    embedder.py
    indexer.py
    qdrant_store.py
    retriever.py
  skills/
    engine.py
    parser.py
  tools/
    sandbox.py
  watcher/
    markdown_watcher.py
vault/
  skills/
    docker_debug.md
scripts/
  ingest_obsidian.py
  run_agent.py
  run_meta_agent.py
  run_multi_agent.py
  run_skill_engine.py
  watch_obsidian.py
```

## Lancement rapide

Demarrer Qdrant:

```bash
docker compose up -d qdrant
```

Indexer le vault:

```bash
.venv/bin/python scripts/ingest_obsidian.py
```

Lancer le watcher Obsidian:

```bash
.venv/bin/python scripts/watch_obsidian.py
```

Lancer l'API:

```bash
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Interroger la memoire:

```bash
curl -X POST http://127.0.0.1:8000/memory \
  -H 'Content-Type: application/json' \
  -d '{"query":"agent memory","limit":6}'
```

Lancer l'agent autonome:

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"task":"summarize project memory","max_rounds":2}'
```

## Commandes utiles

Boucle multi-agent:

```bash
.venv/bin/python scripts/run_multi_agent.py "inspect project tests"
```

Generation de skills:

```bash
.venv/bin/python scripts/run_skill_engine.py "triage qdrant indexing failure"
.venv/bin/python scripts/run_skill_engine.py --improve
```

Meta-agent:

```bash
.venv/bin/python scripts/run_meta_agent.py --limit 50
```

Verification:

```bash
.venv/bin/python -m compileall backend scripts
.venv/bin/python -m unittest tests.test_backend_desktop_api
```

## Variables utiles

```text
ANUBIS_VAULT_PATH=vault
ANUBIS_SKILLS_PATH=vault/skills
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=anubis_chunks
ANUBIS_LLM_MODEL=qwen2.5-coder:7b
OLLAMA_BASE_URL=http://localhost:11434
ANUBIS_TOOL_TIMEOUT_SECONDS=30
ANUBIS_TOOL_LOG_PATH=state/backend_tool_audit.jsonl
```

## Principe de conception

Anubis suit une approche Karpathy-style:

- fichiers Markdown comme source de verite;
- Qdrant comme index semantique regenerable;
- boucles simples et lisibles;
- peu d'abstractions;
- validation avant mutation;
- autonomie progressive et auditable.
