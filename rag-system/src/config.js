import "dotenv/config";

export const config = {
  vaultPath: process.env.OBSIDIAN_VAULT_PATH || "../obsidian_vault",
  qdrantUrl: process.env.QDRANT_URL || "http://127.0.0.1:6333",
  qdrantApiKey: process.env.QDRANT_API_KEY || "",
  qdrantCollection: process.env.QDRANT_COLLECTION || "anubis_vault",
  embeddingProvider: process.env.EMBEDDING_PROVIDER || "placeholder",
  embeddingModel: process.env.EMBEDDING_MODEL || "text-embedding-3-small",
  embeddingDimensions: Number(process.env.EMBEDDING_DIMENSIONS || 1536),
  openaiApiKey: process.env.OPENAI_API_KEY || "",
  llmProvider: process.env.LLM_PROVIDER || "placeholder",
  llmModel: process.env.LLM_MODEL || "gpt-4.1-mini",
  port: Number(process.env.PORT || 8787),
  maxChunkChars: Number(process.env.MAX_CHUNK_CHARS || 1600),
  chunkOverlapChars: Number(process.env.CHUNK_OVERLAP_CHARS || 180)
};
