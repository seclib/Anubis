# ANUBIS CLI

ANUBIS CLI is a Metasploit-style command console for cyber intelligence workflows. It provides interactive modules for OSINT, CVE analysis, bug bounty research, ExploitDB/searchsploit intelligence, discovery dorks, defensive detection mapping, development knowledge, and graph-driven investigations.

The CLI is designed around a `use -> set -> run` workflow:

- Select a module.
- Configure module options.
- Run the module.
- Review structured RAG and graph-backed results.

ANUBIS is intended for local research, defensive analysis, and authorized security work.

## Overview

ANUBIS CLI combines:

- OSINT RAG for domains, IPs, emails, usernames, organizations, and public metadata.
- CVE RAG for vulnerability records, exploitability, KEV status, affected products, and remediation context.
- Bug bounty RAG for vulnerability patterns, payload techniques, bypass notes, and report-derived lessons.
- ExploitDB RAG for searchsploit-style exploit intelligence, CVE references, exploit paths, and vulnerability technique tags.
- Discovery RAG for GHDB entries, Google dorks, GitHub/GitLab dorks, Shodan, Censys, and FOFA query patterns.
- Dev RAG for code, repository, StackOverflow, and error-to-fix workflows.
- Defense RAG for MITRE ATT&CK, IDS rules, detections, mitigations, and response playbooks.
- Graph RAG for relationship-driven investigations across infrastructure, CVEs, organizations, and threat entities.
- Optional Docker tooling for local Metasploit, BloodHound, and Neo4j workflows.

## Core Intelligence Modules

- OSINT RAG
- CVE RAG
- Bug Bounty RAG
- ExploitDB RAG
- Discovery RAG
- Dev RAG
- Defense RAG
- Graph RAG

## Optional Tool Integrations

- Metasploit (Docker)
- BloodHound (Docker)
- Neo4j
- Searchsploit

The console prompt follows a Metasploit-like style:

```text
anubis >
anubis (osint/recon) >
```

## CLI Usage

Start the interactive console:

```bash
python3 anubis-cli/main.py console
```

Show available modules:

```text
anubis > show modules
```

Use the OSINT module:

```text
anubis > use osint
anubis (osint/recon) >
```

Show module options:

```text
anubis (osint/recon) > show options
```

Set a target:

```text
anubis (osint/recon) > set TARGET example.com
```

Run the module:

```text
anubis (osint/recon) > run
```

Return to the global console:

```text
anubis (osint/recon) > back
```

Route a free-form query through the RAG router:

```text
anubis > search CVE-2024-3094 xz backdoor
```

Run a command non-interactively:

```bash
python3 anubis-cli/main.py exec \
  -c "use osint" \
  -c "set TARGET example.com" \
  -c "show options" \
  -c "run"
```

Direct domain queries are also supported:

```bash
python3 anubis-cli/main.py /cve "CVE-2024-3094 exploitability"
python3 anubis-cli/main.py /bugbounty "XSS CSP bypass"
python3 anubis-cli/main.py /tools "nmap quick tcp scan"
```

ExploitDB/searchsploit intelligence is built in:

```text
anubis > exploit search remote command execution
anubis > exploit info 1001
anubis > exploit filter RCE
```

## Docker Optional Stack

ANUBIS includes an optional Docker Compose profile for local security tooling.

Included services:

- Metasploit container for local framework access and isolated workspace storage.
- BloodHound container for Active Directory graph investigation workflows.
- Neo4j backend for BloodHound.

Start the optional security tools stack:

```bash
docker/security-tools/start.sh
```

Check status:

```bash
docker/security-tools/status.sh
```

Stop the stack:

```bash
docker/security-tools/stop.sh
```

Equivalent Compose command:

```bash
docker compose --profile exploit-tools up -d metasploit
docker compose --profile graph-tools up -d bloodhound-neo4j bloodhound
```

Default safety posture:

- Metasploit ports are not published.
- Neo4j ports are not published.
- BloodHound UI is bound to local-only access at `127.0.0.1:8080` by default.
- Security tooling runs on an isolated Docker network.
- Tool data is stored in persistent Docker volumes.

## Architecture Overview

```text
ANUBIS CLI
  |
  |-- Console router
  |     |-- use <module>
  |     |-- set <OPTION> <VALUE>
  |     |-- show options
  |     |-- run
  |
  |-- Dynamic modules
  |     |-- osint/recon
  |     |-- cve/analyze
  |     |-- bugbounty/technique
  |     |-- defense/detect
  |     |-- exploit search/info/filter
  |
  |-- RAG system
  |     |-- query router
  |     |-- OSINT RAG
  |     |-- CVE RAG
  |     |-- BugBounty RAG
  |     |-- ExploitDB RAG
  |     |-- Discovery RAG
  |     |-- Dev RAG
  |     |-- Defense RAG
  |     |-- Graph RAG
  |
  |-- Graph system
  |     |-- Neo4j client
  |     |-- entity relationships
  |     |-- investigation traversals
  |
  |-- Docker tools layer
        |-- Metasploit
        |-- BloodHound
        |-- Neo4j backend
        |-- Searchsploit-compatible ExploitDB data
```

### CLI Layer

The CLI provides an interactive console, command routing, dynamic module loading, option management, and structured output formatting.

### RAG Layer

Modules call the unified RAG client internally. The client supports:

- domain-specific retrieval
- query router integration
- repeated-query caching
- structured results
- CLI-friendly result formatting

### Graph Layer

The graph system supports relationship-centric investigations across domains, IPs, emails, CVEs, organizations, and threat-related entities.

### Docker Tools Layer

The optional Docker stack provides local tool services for workflows that need Metasploit or BloodHound without exposing dangerous ports by default.

## Safety Note

ANUBIS CLI is for local research, defensive security analysis, authorized testing, and controlled lab environments only.

Do not use ANUBIS, Metasploit, BloodHound, or any integrated module against systems, networks, identities, or data you do not own or do not have explicit permission to assess.
