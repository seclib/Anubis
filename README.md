# Anubis Desktop OS

Anubis Desktop OS is a local AI workspace for notes, memory, and an assistant that helps you organize knowledge and work through tasks.

It runs on your Linux computer and gives you a desktop app where you can:

- write and edit notes
- ask an AI assistant questions
- save useful knowledge into memory
- run autonomous agent workflows
- see system health at a glance
- explore skills, agents, and memory through dashboard views

![Anubis Desktop OS dashboard](docs/screenshots/readme-dashboard.png)

## Lancement rapide

```bash
./start.sh
```

Cette commande lance le backend puis le desktop. Les logs du backend sont écrits dans `state/dev_servers/anubis-backend.log`.

Options utiles:

```bash
./start.sh --backend-only
./start.sh --desktop-only
```

## Who It Is For

Anubis is for people who want a local AI workspace that feels more like a personal operating desk than a chat box.

You can use it for:

- project notes
- research collections
- personal knowledge
- planning
- summaries
- AI-assisted writing
- local experimentation

## Key Features

### Desktop Launcher

Open Anubis from your application menu without typing commands.

![Anubis in the application menu](docs/screenshots/readme-application-menu.png)

### Brain Dashboard

See whether Anubis is running, how much memory is available, what the assistant system is doing, and what recent activity happened.

![Brain Dashboard](docs/screenshots/readme-brain-dashboard.png)

### Notes And Memory

Write Markdown notes in the vault. Anubis can use those notes as memory when answering questions.

![Vault and note editor](docs/screenshots/readme-vault-editor.png)

### AI Assistant

Ask questions, summarize notes, turn text into checklists, and use your saved knowledge while working.

![AI assistant panel](docs/screenshots/readme-ai-assistant.png)

### Skill And Cognitive Graph Views

Explore how skills, agents, memory groups, and relationships connect inside Anubis.

![Cognitive Graph View](docs/screenshots/readme-cognitive-graph.png)

### Local First

Anubis is designed to run on your own machine. Your notes and local state live inside the Anubis folder unless you configure another location.

## Installation

The easiest installation path is the one-click installer:

```bash
./install.sh
```

The installer prepares the app, creates the local environment, initializes the vault, configures local memory services, and installs the desktop launcher.

For installer options:

```bash
./install.sh --help
```

Common options:

```bash
./install.sh --no-qdrant
./install.sh --no-system
./install.sh --build-desktop
```

## Quick Start

1. Install Anubis:

   ```bash
   ./install.sh
   ```

2. Open your application menu.

3. Search for **Anubis Desktop OS**.

4. Click the Anubis icon.

5. In the app, click **Start Anubis** if the system is stopped.

6. Open a note from the **Vault** panel.

7. Ask the assistant a question in the **Agent** panel.

![Anubis ready to use](docs/screenshots/readme-ready.png)

## Desktop Launcher

If you only want to install or refresh the desktop menu entry, run:

```bash
scripts/install_desktop_entry.sh
```

This installs:

- the application menu entry
- the Anubis icon
- the launcher wrapper

Supported desktop environments include GNOME, KDE, and XFCE on Debian, Ubuntu, and Kali Linux.

## Backing Up Your Data

To back up your Anubis workspace, copy these folders from the Anubis folder:

- `vault`
- `state`
- `.agents`

Close Anubis before copying them.

## Documentation

- User guide: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- Desktop launcher: [docs/DESKTOP_LAUNCHER.md](docs/DESKTOP_LAUNCHER.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Local API notes: [docs/LOCAL_API.md](docs/LOCAL_API.md)

## Project Status

Anubis is an active local AI desktop project. The current focus is making the desktop app, memory system, assistant workflow, and installer reliable and easy to use.
