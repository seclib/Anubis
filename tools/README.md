# ANUBIS Optional Tools Layer

This directory contains optional tooling integrations for ANUBIS.

The tools layer is not required for the core CLI, RAG system, Qdrant, or Neo4j graph modules. It is opt-in through Docker Compose profiles.

## Profiles

```text
exploit-tools  Metasploit container
graph-tools    BloodHound + Neo4j containers
```

## CLI Commands

Start Metasploit:

```text
anubis > tools start metasploit
```

Start BloodHound and its Neo4j backend:

```text
anubis > tools start bloodhound
```

Stop all optional tool containers:

```text
anubis > tools stop
```

Show optional tool status:

```text
anubis > tools status
```

## Docker Compose

Metasploit only:

```bash
docker compose --profile exploit-tools up -d metasploit
```

BloodHound stack:

```bash
docker compose --profile graph-tools up -d bloodhound-neo4j bloodhound
```

Stop optional tools:

```bash
docker compose --profile exploit-tools --profile graph-tools stop metasploit bloodhound bloodhound-neo4j
```

## Safety Defaults

- Optional tools are disabled unless their profile is started.
- Metasploit exposes no host ports by default.
- BloodHound UI binds to `127.0.0.1:${BLOODHOUND_HTTP_PORT:-8080}`.
- Neo4j is not exposed to the host by default.
- Tool containers use an isolated Docker network.

