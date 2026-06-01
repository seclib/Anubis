import crypto from "node:crypto";
import { config } from "./config.js";

export async function embedTexts(texts) {
  if (config.embeddingProvider === "openai") return embedWithOpenAI(texts);
  return texts.map((text) => placeholderEmbedding(text, config.embeddingDimensions));
}

async function embedWithOpenAI(texts) {
  if (!config.openaiApiKey) throw new Error("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai");

  const response = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.openaiApiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ model: config.embeddingModel, input: texts })
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`OpenAI embeddings failed: ${response.status} ${body}`);
  }

  const payload = await response.json();
  return payload.data.map((item) => item.embedding);
}

function placeholderEmbedding(text, dimensions) {
  const vector = new Array(dimensions).fill(0);
  const tokens = text.toLowerCase().match(/[a-z0-9]+/g) || [];

  for (const token of tokens) {
    const hash = crypto.createHash("sha256").update(token).digest();
    const index = hash.readUInt32BE(0) % dimensions;
    const sign = hash[4] % 2 === 0 ? 1 : -1;
    vector[index] += sign;
  }

  const norm = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0)) || 1;
  return vector.map((value) => value / norm);
}
