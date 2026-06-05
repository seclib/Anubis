import { App, Notice, Plugin, PluginSettingTab, Setting, TFile } from "obsidian";

interface AnubisSyncSettings {
  endpoint: string;
}

const DEFAULT_SETTINGS: AnubisSyncSettings = {
  endpoint: "http://127.0.0.1:8787/sync"
};

interface SyncNote {
  id: string;
  path: string;
  title: string;
  content: string;
  updatedAt: string;
}

export default class AnubisSyncPlugin extends Plugin {
  settings: AnubisSyncSettings = DEFAULT_SETTINGS;

  async onload() {
    await this.loadSettings();

    this.addCommand({
      id: "sync-vault-to-anubis",
      name: "Sync Vault to Anubis",
      callback: () => this.syncVault()
    });

    this.addSettingTab(new AnubisSyncSettingTab(this.app, this));
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  async syncVault() {
    const notice = new Notice("Syncing vault to Anubis...", 0);

    try {
      const notes = await this.readMarkdownNotes();
      const response = await fetch(this.settings.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "obsidian-plugin",
          syncedAt: new Date().toISOString(),
          notes
        })
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(`Anubis sync failed: ${response.status} ${body}`);
      }

      const result = await response.json();
      notice.hide();
      new Notice(`Anubis sync complete: ${result.notes ?? notes.length} notes`, 5000);
    } catch (error) {
      notice.hide();
      new Notice(error instanceof Error ? error.message : "Anubis sync failed", 8000);
      console.error(error);
    }
  }

  async readMarkdownNotes(): Promise<SyncNote[]> {
    const files = this.app.vault.getMarkdownFiles();
    const notes: SyncNote[] = [];

    for (const file of files) {
      try {
        notes.push(await this.readMarkdownNote(file));
      } catch (error) {
        console.error(`Failed to read ${file.path}`, error);
      }
    }

    return notes;
  }

  async readMarkdownNote(file: TFile): Promise<SyncNote> {
    const content = await this.app.vault.cachedRead(file);
    return {
      id: file.path,
      path: file.path,
      title: file.basename,
      content,
      updatedAt: new Date(file.stat.mtime).toISOString()
    };
  }
}

class AnubisSyncSettingTab extends PluginSettingTab {
  plugin: AnubisSyncPlugin;

  constructor(app: App, plugin: AnubisSyncPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Anubis Sync" });

    new Setting(containerEl)
      .setName("Sync endpoint")
      .setDesc("Backend endpoint that receives vault sync payloads.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.endpoint)
          .setValue(this.plugin.settings.endpoint)
          .onChange(async (value) => {
            this.plugin.settings.endpoint = value.trim() || DEFAULT_SETTINGS.endpoint;
            await this.plugin.saveSettings();
          })
      );
  }
}
