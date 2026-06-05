import crypto from "node:crypto";
import { config } from "./config.js";

export class QdrantStore {
  constructor(options = {}) {
    this.url = options.url || config.qdrantUrl;
    this.apiKey = options.apiKey || config.qdrantApiKey;
    this.collection = options.collection || config.qdrantCollection;
    this.dimensions = options.dimensions || config.embeddingDimensions;
  }

  async ensureCollection() {
    const exists = await this.request(`/collections/${this.collection}`, { method: "GET", ok: [200, 404] });
    if (exists.status === 200) return;

    await this.request(`/collections/${this.collection}`, {
      method: "PUT",
      body: {
        vectors: {
          size: this.dimensions,
          distance: "Cosine"
        }
      }
    });
  }

  async deleteNote(noteId) {
    await this.request(`/collections/${this.collection}/points/delete`, {
      method: "POST",
      body: {
        filter: {
          must: [{ key: "noteId", match: { value: noteId } }]
        }
      }
    });
  }

  async upsertChunks(chunks, vectors) {
    if (chunks.length !== vectors.length) throw new Error("chunks and vectors length mismatch");
    const points = chunks.map((chunk, index) => ({
      id: stablePointId(chunk.id),
      vector: vectors[index],
      payload: {
        ...chunk.payload,
        chunkId: chunk.id,
        text: chunk.text
      }
    }));

    if (!points.length) return;
    await this.request(`/collections/${this.collection}/points?wait=true`, {
      method: "PUT",
      body: { points }
    });
  }

  async search(vector, limit = 8) {
    const result = await this.request(`/collections/${this.collection}/points/search`, {
      method: "POST",
      body: {
        vector,
        limit,
        with_payload: true
      }
    });

    return result.body.result || [];
  }

  async request(path, options = {}) {
    const headers = { "Content-Type": "application/json" };
    if (this.apiKey) headers["api-key"] = this.apiKey;

    const response = await fetch(`${this.url}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined
    });

    const ok = options.ok || [200, 201];
    const text = await response.text();
    const body = text ? JSON.parse(text) : {};

    if (!ok.includes(response.status)) {
      throw new Error(`Qdrant request failed: ${response.status} ${JSON.stringify(body)}`);
    }

    return { status: response.status, body };
  }
}

function stablePointId(value) {
  const hex = crypto.createHash("sha256").update(value).digest("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
}
