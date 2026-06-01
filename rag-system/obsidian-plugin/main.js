var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/main.ts
var main_exports = {};
__export(main_exports, {
  default: () => AnubisSyncPlugin
});
module.exports = __toCommonJS(main_exports);
var import_obsidian = require("obsidian");
var DEFAULT_SETTINGS = {
  endpoint: "http://127.0.0.1:8787/sync"
};
var AnubisSyncPlugin = class extends import_obsidian.Plugin {
  constructor() {
    super(...arguments);
    this.settings = DEFAULT_SETTINGS;
  }
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
    var _a;
    const notice = new import_obsidian.Notice("Syncing vault to Anubis...", 0);
    try {
      const notes = await this.readMarkdownNotes();
      const response = await fetch(this.settings.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "obsidian-plugin",
          syncedAt: (/* @__PURE__ */ new Date()).toISOString(),
          notes
        })
      });
      if (!response.ok) {
        const body = await response.text();
        throw new Error(`Anubis sync failed: ${response.status} ${body}`);
      }
      const result = await response.json();
      notice.hide();
      new import_obsidian.Notice(`Anubis sync complete: ${(_a = result.notes) != null ? _a : notes.length} notes`, 5e3);
    } catch (error) {
      notice.hide();
      new import_obsidian.Notice(error instanceof Error ? error.message : "Anubis sync failed", 8e3);
      console.error(error);
    }
  }
  async readMarkdownNotes() {
    const files = this.app.vault.getMarkdownFiles();
    const notes = [];
    for (const file of files) {
      try {
        notes.push(await this.readMarkdownNote(file));
      } catch (error) {
        console.error(`Failed to read ${file.path}`, error);
      }
    }
    return notes;
  }
  async readMarkdownNote(file) {
    const content = await this.app.vault.cachedRead(file);
    return {
      id: file.path,
      path: file.path,
      title: file.basename,
      content,
      updatedAt: new Date(file.stat.mtime).toISOString()
    };
  }
};
var AnubisSyncSettingTab = class extends import_obsidian.PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }
  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Anubis Sync" });
    new import_obsidian.Setting(containerEl).setName("Sync endpoint").setDesc("Backend endpoint that receives vault sync payloads.").addText(
      (text) => text.setPlaceholder(DEFAULT_SETTINGS.endpoint).setValue(this.plugin.settings.endpoint).onChange(async (value) => {
        this.plugin.settings.endpoint = value.trim() || DEFAULT_SETTINGS.endpoint;
        await this.plugin.saveSettings();
      })
    );
  }
};
