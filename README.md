# Anubis

Agent CLI autonome local inspire des systemes type Claude Code, Hermes CLI et OpenDevin.

Anubis execute des taches de developpement avec Ollama, une boucle agent, des tools Linux, une memoire locale, une API compatible OpenAI et une interface terminal interactive.

Le projet est en phase de stabilisation architecture. La priorite actuelle est la robustesse, pas l'ajout de nouvelles fonctionnalites.

## Objectifs

- Executer localement avec Ollama, sans dependance cloud obligatoire.
- Fournir un agent CLI capable de lire, modifier, tester et analyser un projet.
- Garder une architecture maintenable : agent, tools, executor, memory et LLM doivent rester separes.
- Eviter les circular imports et les dependances bidirectionnelles.
- Garantir qu'une execution agent retourne toujours une reponse finale utilisateur.
- Preparer un systeme extensible avec plugins, multi-agents et streaming propre.

## Etat Actuel

Anubis contient deja :

- une boucle agent autonome dans `agent/loop.py`
- une integration Ollama dans `llm/ollama.py`
- un executor de tools dans `executor/tool_executor.py`
- des tools filesystem, shell, git, repo, memoire et developpement autonome
- une memoire courte/longue dans `memory/`
- une API FastAPI compatible OpenAI dans `app/main.py`
- une API HTTP alternative dans `api/openai_server.py`
- une interface CLI riche dans `anubis_cli.py`
- un mode Docker avec Qdrant optionnel
- un jeu de tests d'autonomie dans `tests/test_loop_autonomy.py`

Point important : le projet n'a pas actuellement de circular imports critiques detectes entre les couches principales. Le risque principal est plutot la concentration de responsabilites dans certains modules, surtout `agent/loop.py` et `anubis_cli.py`.

## Architecture Actuelle

```text
.
├── agent/
│   ├── loop.py              # boucle agent principale
│   ├── dependencies.py      # injection de dependances
│   ├── prompts.py           # prompts systeme
│   ├── parser.py            # parsing des actions JSON
│   ├── planner.py           # planification simple
│   ├── multi_agent.py       # profils agents et routage multi-agent
│   ├── orchestrator_agent.py
│   ├── coder_agent.py
│   ├── reviewer_agent.py
│   ├── tester_agent.py
│   └── debugger_agent.py
├── app/
│   └── main.py              # API FastAPI
├── api/
│   └── openai_server.py     # serveur OpenAI-compatible alternatif
├── core/
│   └── workspace.py         # securisation des chemins workspace
├── executor/
│   └── tool_executor.py     # execution et registre des tools
├── llm/
│   └── ollama.py            # appels Ollama /api/chat
├── memory/
│   ├── state.py             # memoire runtime JSON
│   ├── hermes.py            # memoire long terme
│   └── vector.py            # memoire vectorielle
├── tools/
│   ├── filesystem.py
│   ├── terminal.py
│   ├── repo.py
│   ├── sandbox.py
│   ├── git_autonomy.py
│   ├── dynamic_tools.py
│   └── autonomous_developer.py
├── tests/
│   └── test_loop_autonomy.py
├── anubis_cli.py            # terminal interactif
├── main.py                  # entree CLI/API historique
├── config.py                # configuration centrale
├── docker-compose.yml
└── requirements.txt
```

## Regles D'Architecture

Ces regles doivent rester vraies pour garder Anubis maintenable.

```text
CLI/API        -> agent runtime
agent          -> llm, executor, memory, core
executor       -> tools, core
tools          -> core uniquement
memory         -> core uniquement
llm            -> core/config uniquement
core           -> aucune couche domaine
```

Interdictions :

- `tools` ne doit jamais importer `agent`.
- `executor` ne doit jamais importer `agent`.
- `memory` ne doit jamais importer `agent`, `executor` ou `tools`.
- `llm` ne doit pas stocker d'etat conversationnel.
- `cli` ne doit pas contenir de logique de raisonnement agent.
- un tool ne doit pas appeler directement un autre tool via l'agent.
- toute execution tool doit passer par l'executor.
- toute sortie utilisateur finale doit passer par la boucle/finalisation agent.

## Architecture Cible

La cible de stabilisation est une architecture plus proche d'un produit agent local.

```text
anubis/
├── core/
│   ├── config.py
│   ├── events.py
│   ├── errors.py
│   ├── logging.py
│   └── workspace.py
├── runtime/
│   ├── container.py
│   └── dependencies.py
├── agent/
│   ├── loop.py
│   ├── state.py
│   ├── router.py
│   ├── planner.py
│   ├── reflector.py
│   ├── finalizer.py
│   ├── safeguards.py
│   └── prompts/
├── orchestrator/
│   ├── orchestrator.py
│   ├── agent_registry.py
│   ├── model_policy.py
│   └── task_graph.py
├── executor/
│   ├── executor.py
│   ├── registry.py
│   ├── schemas.py
│   └── permissions.py
├── tools/
├── memory/
│   ├── short_term.py
│   ├── long_term.py
│   ├── vector.py
│   ├── compaction.py
│   └── schemas.py
├── llm/
│   ├── ollama.py
│   ├── messages.py
│   ├── model_registry.py
│   └── streaming.py
├── plugins/
│   ├── loader.py
│   ├── manifest.py
│   └── sandbox.py
├── cli/
│   ├── main.py
│   ├── renderer.py
│   ├── commands.py
│   ├── session.py
│   └── streaming.py
└── api/
    ├── routes.py
    ├── schemas.py
    └── stream.py
```

## Boucle Agent Recommandee

```text
user input
  -> observe
  -> route
  -> plan if needed
  -> act with tools if needed
  -> reflect
  -> finalize
  -> user response
```

Invariant de production :

> Une execution agent doit toujours atteindre une etape `finalize`, meme si un tool echoue, si Ollama retourne une reponse invalide, si la memoire est indisponible ou si la limite de steps est atteinte.

Les safeguards attendus :

- `MAX_STEPS`
- `MAX_RETRIES`
- `MAX_TOOL_RETRIES`
- timeout par commande shell
- limite de taille stdout/stderr
- detection de non-progres
- reponse finale obligatoire
- erreurs structurees et journalisees

## Installation Locale

### 1. Prerequis

- Linux
- Python 3.10+
- Ollama
- Git
- Docker optionnel

### 2. Installer les dependances Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Installer le modele Ollama recommande

```bash
ollama pull qwen2.5-coder:7b
ollama pull bge-m3
```

Demarrer Ollama si necessaire :

```bash
ollama serve
```

### 4. Configurer l'environnement

```bash
cp .env.example .env
```

Configuration minimale :

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_FALLBACK_MODEL=qwen2.5-coder:7b
PROJECT_ROOT=.
WORKSPACE_ROOT=.
```

## Lancer Anubis

### Terminal interactif

```bash
python3 anubis_cli.py
```

Commandes utiles dans le terminal :

```text
/help                 afficher les commandes
/run <tache>          lancer la boucle agent autonome
/exec <commande>      executer une commande shell controlee
/status              afficher l'etat memoire
/clear               vider le contexte CLI
/exit                quitter
```

### Agent depuis Python

```python
from agent.loop import run_agent_loop

result = run_agent_loop("Analyse le projet et propose les priorites de refactor")
print(result)
```

### API locale

```bash
python3 main.py serve
```

Endpoint par defaut :

```text
http://localhost:8000/v1
```

Endpoints principaux :

```text
GET  /v1/models
GET  /v1/models/{model_id}
POST /v1/chat/completions
POST /v1/agent/stream
GET  /health
```

Exemple de stream agent :

```bash
curl -N http://localhost:8000/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"task":"Inspecte le projet et resume les points d entree"}'
```

### Docker

```bash
docker compose up --build
```

Le compose lance :

- `anubis-agent` sur `http://localhost:8000/v1`
- `qdrant` sur `http://localhost:6333`

Dans Docker, Anubis contacte Ollama via :

```text
http://host.docker.internal:11434
```

## Configuration Principale

Variables importantes :

```bash
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_FALLBACK_MODEL=qwen2.5-coder:7b
OLLAMA_NUM_CTX=8192
OLLAMA_KEEP_ALIVE=1h
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=4096

# Agents
ORCHESTRATOR_AGENT_MODEL=$OLLAMA_MODEL
PLANNER_AGENT_MODEL=$OLLAMA_MODEL
CODER_AGENT_MODEL=$OLLAMA_MODEL
REVIEWER_AGENT_MODEL=$OLLAMA_MODEL
TESTER_AGENT_MODEL=$OLLAMA_MODEL
DEBUGGER_AGENT_MODEL=$OLLAMA_MODEL
MEMORY_AGENT_MODEL=$OLLAMA_MODEL

# Loop
MAX_STEPS=30
MAX_RETRIES=3
MAX_TOOL_RETRIES=3
CONTINUOUS_RUN=false

# Tools
TOOL_COMMAND_TIMEOUT=120
TOOL_COMMAND_MAX_LENGTH=4000
TOOL_OUTPUT_MAX_CHARS=20000
TOOL_AUDIT_FILE=state/tool_audit.log

# Memory
HERMES_MEMORY_ENABLED=true
HERMES_MEMORY_BACKEND=local
HERMES_MEMORY_FILE=state/hermes_memory.json
EMBEDDING_MODEL=bge-m3
VECTOR_STORE_FILE=state/vector_store.json

# API
API_HOST=127.0.0.1
API_PORT=8000
API_BASE_PATH=/v1
API_AUTH_REQUIRED=false
API_MODEL_ID=claude-code-local
```

## Tools Disponibles

Familles de tools :

- filesystem : lire, ecrire, lister des fichiers
- terminal : executer des commandes shell controlees
- repo : introspection projet, detection frameworks, entrypoints
- git : status, validations, commit autonome, rollback
- vector memory : indexation repo et recherche semantique
- Hermes memory : stockage et recherche memoire long terme
- dynamic tools : creation et chargement de tools Python controles
- autonomous developer : build, tests, serveurs locaux, scaffolding

Tous les tools doivent rester atomiques, testables et sans dependance vers `agent`.

## Memoire

Anubis utilise plusieurs niveaux de memoire :

- `state/runtime.json` : etat runtime, historique, progression
- `state/hermes_memory.json` : memoire long terme locale
- `state/vector_store.json` : index vectoriel local
- Qdrant optionnel via `HERMES_MEMORY_BACKEND=qdrant`
- Obsidian optionnel via `OBSIDIAN_VAULT_PATH`

Regles de stabilite :

- les messages doivent toujours avoir un format clair `role/content`
- la memoire ne doit pas contenir de logique agent
- la compaction doit eviter les contextes trop longs
- les erreurs memoire ne doivent jamais bloquer la reponse finale

## Observabilite

Fichiers utiles :

```text
state/cli.log
state/tool_audit.log
state/runtime.json
```

Bonnes pratiques attendues :

- logs structures par run agent
- events de streaming typables
- audit de chaque tool call
- distinction claire entre erreur tool, erreur LLM, erreur memory et erreur loop
- conservation d'un `run_id`, `step_id` et `tool_call_id`

## Tests Et Verification

Lancer les tests :

```bash
python3 -m unittest tests/test_loop_autonomy.py
```

Verifier les imports Python :

```bash
python3 -m py_compile \
  config.py \
  llm/ollama.py \
  agent/prompts.py \
  agent/loop.py \
  executor/tool_executor.py \
  anubis_cli.py
```

Verifier la configuration Docker :

```bash
docker compose config
```

Verifier Ollama :

```bash
ollama list
curl http://localhost:11434/api/tags
```

## Roadmap De Stabilisation

Priorite 1 : boucle agent robuste

- extraire `agent/router.py`
- extraire `agent/state.py`
- extraire `agent/finalizer.py`
- ajouter un etat final obligatoire
- rendre les side effects git non bloquants pour la reponse finale

Priorite 2 : contrats internes

- creer `ToolCall` et `ToolResult`
- creer `AgentEvent`
- creer `MemoryMessage`
- normaliser les messages LLM
- ajouter des erreurs domaine explicites

Priorite 3 : executor et plugin system

- separer `executor/executor.py` et `executor/registry.py`
- deplacer les permissions tool dans un module dedie
- ajouter manifest plugin
- permettre activation/desactivation de tools

Priorite 4 : CLI production

- decouper `anubis_cli.py`
- isoler renderer, commands, session et streaming
- afficher les tool calls via events structures
- garder la logique agent hors du terminal

Priorite 5 : observabilite

- logs JSON optionnels
- traces par run
- metriques par tool
- rapport d'echec final explicite

## Principes De Developpement

- Robustesse avant nouvelles fonctionnalites.
- Dependency injection avant imports globaux.
- LLM stateless.
- Memory isolee.
- Executor independant.
- Tools sans connaissance de l'agent.
- Une seule direction de dependance.
- Une reponse finale utilisateur est obligatoire.

## Statut

Anubis est un prototype avance d'agent autonome local. Il est fonctionnel, mais la prochaine etape importante est la stabilisation de son architecture interne pour le rendre production-ready.

