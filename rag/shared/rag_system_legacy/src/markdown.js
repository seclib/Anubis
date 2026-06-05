import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import fg from "fast-glob";
import matter from "gray-matter";
import { config } from "./config.js";

export async function listMarkdownFiles(vaultPath) {
  return fg("**/*.md", {
    cwd: vaultPath,
    absolute: true,
    onlyFiles: true,
    dot: false,
    ignore: [".obsidian/**", ".trash/**", "node_modules/**"]
  });
}

export async function readMarkdownNote(filePath, vaultPath) {
  const raw = await fs.readFile(filePath, "utf8");
  const parsed = matter(raw);
  const relativePath = path.relative(vaultPath, filePath).split(path.sep).join("/");
  const title = parsed.data.title || path.basename(relativePath, ".md");
  return {
    id: noteId(relativePath),
    path: relativePath,
    title,
    frontmatter: parsed.data || {},
    content: parsed.content.trim(),
    raw,
    checksum: sha256(raw),
    updatedAt: (await fs.stat(filePath)).mtime.toISOString()
  };
}

export function parseWikilinks(text) {
  const links = [];
  const pattern = /\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g;
  let match;
  while ((match = pattern.exec(text))) {
    links.push({ target: match[1].trim(), alias: match[2]?.trim() || null });
  }
  return links;
}

export function parseTags(text) {
  return [...new Set((text.match(/(^|\s)#([A-Za-z0-9/_-]+)/g) || []).map((tag) => tag.trim().replace(/^#/, "")))];
}

export function chunkNote(note, options = {}) {
  const maxChars = options.maxChunkChars || config.maxChunkChars;
  const overlap = options.chunkOverlapChars || config.chunkOverlapChars;
  const blocks = splitByHeadings(note.content);
  const chunks = [];

  for (const block of blocks) {
    if (block.text.length <= maxChars) {
      chunks.push(toChunk(note, block.heading, block.text, chunks.length));
      continue;
    }

    let start = 0;
    while (start < block.text.length) {
      const end = Math.min(start + maxChars, block.text.length);
      const slice = block.text.slice(start, end).trim();
      if (slice) chunks.push(toChunk(note, block.heading, slice, chunks.length));
      if (end === block.text.length) break;
      start = Math.max(0, end - overlap);
    }
  }

  return chunks;
}

function splitByHeadings(content) {
  const lines = content.split(/\r?\n/);
  const sections = [];
  let heading = "Document";
  let buffer = [];

  for (const line of lines) {
    const match = /^(#{1,6})\s+(.+)$/.exec(line);
    if (match && buffer.join("\n").trim()) {
      sections.push({ heading, text: buffer.join("\n").trim() });
      heading = match[2].trim();
      buffer = [line];
    } else {
      if (match) heading = match[2].trim();
      buffer.push(line);
    }
  }

  if (buffer.join("\n").trim()) sections.push({ heading, text: buffer.join("\n").trim() });
  return sections.length ? sections : [{ heading: "Document", text: content }];
}

function toChunk(note, heading, text, index) {
  const chunkId = `${note.id}:${index}:${sha256(text).slice(0, 12)}`;
  return {
    id: chunkId,
    text,
    payload: {
      noteId: note.id,
      path: note.path,
      title: note.title,
      heading,
      chunkIndex: index,
      checksum: note.checksum,
      updatedAt: note.updatedAt,
      tags: parseTags(note.raw),
      links: parseWikilinks(note.raw)
    }
  };
}

function noteId(relativePath) {
  return sha256(relativePath).slice(0, 24);
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}
