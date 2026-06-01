# Anubis Desktop OS User Guide

This guide is for people who want to use Anubis from the desktop, with simple steps and plain language.

Anubis Desktop OS is a local workspace for notes, memory, and an AI assistant. You can write notes, ask questions, search your saved knowledge, and watch the system status from one desktop app.

## 1. Installation

### Install the desktop launcher

1. Open the Anubis folder.
2. Find the desktop installer in the `scripts` folder.
3. Run the installer once.
4. After installation, look for **Anubis Desktop OS** in your application menu.

Screenshot placeholder:

![Anubis installer location](screenshots/user-guide-installer-location.png)

### Where Anubis appears

After installation, Anubis should appear in your desktop application menu.

It works with common Linux desktops such as:

- GNOME
- KDE
- XFCE

Screenshot placeholder:

![Anubis in the application menu](screenshots/user-guide-app-menu.png)

## 2. First Launch

1. Open your application menu.
2. Search for **Anubis Desktop OS**.
3. Click the Anubis icon.
4. Wait for the main window to open.

Screenshot placeholder:

![Anubis first launch](screenshots/user-guide-first-launch.png)

When Anubis opens, you will see a dashboard. The dashboard shows whether the main parts of Anubis are ready.

Look for these areas:

- **System Health**: shows whether the main parts of Anubis are running.
- **Memory Overview**: shows your notes and saved memory.
- **Agent Activity**: shows what the assistant system is doing.
- **Live Logs**: shows recent activity.
- **Vault**: where your notes live.
- **Agent**: where you talk to the AI assistant.

If some items say **starting**, wait a short moment. Anubis may need time to wake up.

## 3. Creating Notes

Notes are the main way to store information in Anubis.

### Open an existing note

1. Look at the **Vault** area on the left side.
2. Click a note name.
3. The note opens in the editor.

Screenshot placeholder:

![Opening a note](screenshots/user-guide-open-note.png)

### Edit a note

1. Click inside the note editor.
2. Type your changes.
3. Click **Save**.

Screenshot placeholder:

![Editing a note](screenshots/user-guide-edit-note.png)

### What to write in notes

You can write anything useful, such as:

- Project ideas
- Research notes
- Daily plans
- Decisions you want to remember
- Personal instructions for Anubis
- Summaries of important work

Keep notes simple. Short, clear notes are easier for Anubis to use later.

## 4. Using the AI Assistant

The AI assistant is in the **Agent** area.

### Ask a question

1. Find the **Agent** panel.
2. Type your question.
3. Click **Send**.
4. Read the answer.

Screenshot placeholder:

![Asking the assistant](screenshots/user-guide-agent-question.png)

Example questions:

- What do I know about this project?
- Summarize my notes about Anubis.
- Help me plan the next step.
- What did I write about memory?
- Turn this note into a checklist.

### Use selected text

You can send part of a note to memory.

1. Open a note.
2. Highlight the text you want Anubis to remember.
3. Click **Inject selection**.
4. Anubis will add that text to its working memory.

Screenshot placeholder:

![Injecting selected text](screenshots/user-guide-inject-selection.png)

## 5. Understanding Memory

Anubis memory is built from your notes and saved knowledge.

Think of memory as a helpful library:

- **Notes** are the pages you write.
- **Memory pieces** are smaller parts of your notes that Anubis can search.
- **Search helpers** help Anubis find related ideas.
- **The vault** is the folder where your notes are stored.

You do not need to manage these pieces by hand. The dashboard shows them so you can understand what Anubis sees.

Screenshot placeholder:

![Memory overview](screenshots/user-guide-memory-overview.png)

### How memory helps

When you ask the assistant a question, Anubis can look through saved notes and use relevant information in the answer.

For best results:

1. Write clear notes.
2. Save important details.
3. Use titles that describe the topic.
4. Keep related information together.

## 6. Skill System Overview

Skills are reusable abilities that help Anubis work in a more organized way.

You can think of skills like instruction cards. Each skill tells Anubis how to handle a kind of task.

Examples:

- Remembering information
- Searching notes
- Reviewing work
- Planning steps
- Improving future answers

The dashboard may show a **Skill Ecosystem** or **Cognitive Graph** view. These views help you see how skills, agents, and memory are connected.

Screenshot placeholder:

![Skill system overview](screenshots/user-guide-skill-system.png)

You do not need to edit skills to use Anubis. They are shown so you can understand how Anubis is organized.

## 7. Backup and Restore

Your notes and local memory are important. Back them up regularly.

### What to back up

Back up these folders and files from your Anubis folder:

- `vault`
- `state`
- `.agents`

Screenshot placeholder:

![Backup folders](screenshots/user-guide-backup-folders.png)

### Simple backup

1. Close Anubis.
2. Open your file manager.
3. Go to the Anubis folder.
4. Copy the folders listed above.
5. Paste them into a safe place, such as an external drive or backup folder.

### Restore from backup

1. Close Anubis.
2. Open your backup location.
3. Copy your backed-up folders.
4. Paste them back into the Anubis folder.
5. Open Anubis again.

If your file manager asks whether to replace files, only continue if you are sure the backup is the version you want.

## 8. Troubleshooting

### Anubis does not appear in the application menu

Try this:

1. Log out and log back in.
2. Search for **Anubis Desktop OS** again.
3. If it still does not appear, run the desktop installer again.

Screenshot placeholder:

![Searching for Anubis](screenshots/user-guide-search-menu.png)

### The app opens but some parts are stopped

1. Open Anubis.
2. Look at the top control area.
3. Click **Start Anubis**.
4. Wait for the status tiles to update.

Some parts may take a little time to start.

### The assistant does not answer

Try this:

1. Check **System Health**.
2. Make sure the main Anubis service is running.
3. Click **Restart** in the launcher area.
4. Wait a moment.
5. Ask the question again.

### Notes do not appear

Try this:

1. Check the **Vault** panel.
2. Click the refresh button.
3. Make sure your notes are saved.
4. Restart Anubis if the list still looks empty.

### Memory count looks wrong

Memory numbers may take time to update after changes.

Try this:

1. Save your note.
2. Wait a moment.
3. Refresh or restart Anubis.
4. Check the **Memory Overview** again.

### The icon is missing

Try this:

1. Run the desktop installer again.
2. Log out and log back in.
3. Search for **Anubis Desktop OS**.

Some desktops refresh icons slowly.

### The window opens but looks blank

Try this:

1. Close Anubis.
2. Open Anubis again.
3. If it still looks blank, restart your computer.
4. Launch Anubis again from the application menu.

## Quick Start Checklist

1. Install the desktop launcher.
2. Open **Anubis Desktop OS** from the application menu.
3. Click **Start Anubis** if parts of the app are stopped.
4. Open or create notes in the vault.
5. Ask the assistant a question.
6. Save useful information as notes.
7. Back up your `vault`, `state`, and `.agents` folders regularly.

Screenshot placeholder:

![Anubis ready to use](screenshots/user-guide-ready.png)
