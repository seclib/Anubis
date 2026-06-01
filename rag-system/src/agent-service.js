import express from "express";
import { fileURLToPath } from "node:url";
import { config } from "./config.js";
import { embedTexts } from "./embeddings.js";
import { chunkNote } from "./markdown.js";
import { QdrantStore } from "./qdrant.js";

const app = express();
const store = new QdrantStore();

app.use(express.json({ limit: "25mb" }));

app.get("/health", (_request, response) => {
  response.json({ ok: true, service: "anubis-rag" });
});

app.post("/sync", async (request, response) => {
  try {
    await store.ensureCollection();
    const notes = normalizeSyncPayload(request.body);
    let chunksIndexed = 0;

    for (const note of notes) {
      const chunks = chunkNote({
        id: note.id,
        path: note.path,
        title: note.title,
        frontmatter: note.frontmatter || {},
        raw: note.content,
        content: note.content,
        checksum: note.checksum || note.id,
        updatedAt: note.updatedAt || new Date().toISOString()
      });
      const vectors = await embedTexts(chunks.map((chunk) => chunk.text));
      await store.deleteNote(note.id);
      await store.upsertChunks(chunks, vectors);
      chunksIndexed += chunks.length;
    }

    response.json({ status: "synced", notes: notes.length, chunks: chunksIndexed });
  } catch (error) {
    response.status(500).json({ error: error.message });
  }
});

app.post("/search", async (request, response) => {
  try {
    const query = requiredString(request.body?.query, "query");
    const limit = Number(request.body?.limit || 8);
    const results = await retrieveContext(query, limit);
    response.json({ results });
  } catch (error) {
    response.status(400).json({ error: error.message });
  }
});

app.post("/ask", async (request, response) => {
  try {
    const question = requiredString(request.body?.question, "question");
    const context = await retrieveContext(question, Number(request.body?.limit || 8));
    const prompt = buildReasoningPrompt(question, context);
    const answer = await reasonOverContext(prompt, question, context);
    response.json({ answer, context });
  } catch (error) {
    response.status(500).json({ error: error.message });
  }
});

export async function retrieveContext(query, limit = 8) {
  const [vector] = await embedTexts([query]);
  const hits = await store.search(vector, limit);
  return hits
    .map((hit) => ({
      score: hit.score,
      title: hit.payload.title,
      path: hit.payload.path,
      heading: hit.payload.heading,
      text: hit.payload.text,
      tags: hit.payload.tags || [],
      links: hit.payload.links || []
    }))
    .sort((a, b) => b.score - a.score);
}

export function buildReasoningPrompt(question, context) {
  const sources = context
    .map((item, index) => {
      return `SOURCE ${index + 1}
title: ${item.title}
path: ${item.path}
heading: ${item.heading}
score: ${item.score}
content:
${item.text}`;
    })
    .join("\n\n---\n\n");

  return `You are Anubis, a careful Claude-like AI reasoning system.
Use only the provided Obsidian vault context unless you clearly label outside knowledge.
Prefer direct, structured answers.
Cite note paths when claims depend on vault content.
If the vault context is insufficient, say what is missing.

QUESTION:
${question}

VAULT CONTEXT:
${sources || "No relevant vault context found."}

Return:
1. Answer
2. Evidence
3. Gaps or uncertainty
4. Suggested next note/action`;
}

export async function reasonOverContext(prompt, question, context) {
  if (config.llmProvider === "openai") return reasonWithOpenAI(prompt);

  const evidence = context
    .slice(0, 5)
    .map((item) => `- ${item.title} (${item.path}): ${item.text.slice(0, 240).replace(/\s+/g, " ")}${item.text.length > 240 ? "..." : ""}`)
    .join("\n");

  return `1. Answer
The vault context most relevant to "${question}" is concentrated in ${context.length} retrieved note section(s). Use the evidence below as the grounded basis for the answer.

2. Evidence
${evidence || "- No relevant vault context was found."}

3. Gaps or uncertainty
${context.length ? "- This placeholder reasoner does not call an LLM. Set LLM_PROVIDER=openai for generated synthesis." : "- The vault needs more relevant notes or a broader query."}

4. Suggested next note/action
- Review the cited notes, then create or update a concise linked note that captures the answer and related [[wikilinks]].`;
}

async function reasonWithOpenAI(prompt) {
  if (!config.openaiApiKey) throw new Error("OPENAI_API_KEY is required when LLM_PROVIDER=openai");

  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.openaiApiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: config.llmModel,
      messages: [{ role: "user", content: prompt }],
      temperature: 0.2
    })
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`OpenAI chat failed: ${response.status} ${body}`);
  }

  const payload = await response.json();
  return payload.choices?.[0]?.message?.content || "";
}

function normalizeSyncPayload(body) {
  const notes = Array.isArray(body?.notes) ? body.notes : [];
  return notes.map((note) => {
    const path = requiredString(note.path, "note.path");
    const content = requiredString(note.content, "note.content");
    return {
      id: note.id || stableId(path),
      path,
      title: note.title || path.split("/").pop()?.replace(/\.md$/, "") || "Untitled",
      content,
      frontmatter: note.frontmatter || {},
      checksum: note.checksum || stableId(`${path}:${content}`),
      updatedAt: note.updatedAt
    };
  });
}

function requiredString(value, name) {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${name} is required`);
  return value;
}

function stableId(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  return String(hash);
}

export async function startServer() {
  await store.ensureCollection();
  app.listen(config.port, () => {
    console.log(`Anubis RAG service listening on http://127.0.0.1:${config.port}`);
  });
}

const isCli = process.argv[1] === fileURLToPath(import.meta.url);
if (isCli) startServer().catch((error) => {
  console.error(`[agent-service] fatal: ${error.stack || error.message}`);
  process.exit(1);
});
