import path from "node:path";
import { fileURLToPath } from "node:url";
import { config } from "./config.js";
import { embedTexts } from "./embeddings.js";
import { chunkNote, listMarkdownFiles, readMarkdownNote } from "./markdown.js";
import { QdrantStore } from "./qdrant.js";

export async function ingestVault(vaultPath = config.vaultPath) {
  const absoluteVaultPath = path.resolve(vaultPath);
  const store = new QdrantStore();
  await store.ensureCollection();

  const files = await listMarkdownFiles(absoluteVaultPath);
  const summary = { files: files.length, notesIndexed: 0, chunksIndexed: 0, errors: [] };

  for (const file of files) {
    try {
      const note = await readMarkdownNote(file, absoluteVaultPath);
      const chunks = chunkNote(note);
      const vectors = await embedTexts(chunks.map((chunk) => chunk.text));

      await store.deleteNote(note.id);
      await store.upsertChunks(chunks, vectors);

      summary.notesIndexed += 1;
      summary.chunksIndexed += chunks.length;
    } catch (error) {
      summary.errors.push({ file, error: error.message });
      console.error(`[ingest] failed ${file}: ${error.message}`);
    }
  }

  return summary;
}

async function main() {
  const vaultPath = process.argv[2] || config.vaultPath;
  const summary = await ingestVault(vaultPath);
  console.log(JSON.stringify(summary, null, 2));
  if (summary.errors.length) process.exitCode = 1;
}

const isCli = process.argv[1] === fileURLToPath(import.meta.url);
if (isCli) main().catch((error) => {
  console.error(`[ingest] fatal: ${error.stack || error.message}`);
  process.exit(1);
});
