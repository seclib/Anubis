from backend.agent.memory import MarkdownMemory
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.tools import AgentTools


class AgentLoop:
    def __init__(self) -> None:
        self.tools = AgentTools()
        self.memory = MarkdownMemory()
        self.system_prompt = SYSTEM_PROMPT

    def chat(self, message: str) -> dict[str, object]:
        chunks = self.tools.rag_query(message)

        answer = self._answer_from_chunks(message, chunks)
        if message.lower().startswith("remember:"):
            target = self.memory.inject(message.split(":", 1)[1].strip())
            answer = f"Connaissance injectee dans {target}."

        return {
            "answer": answer,
            "chunks_used": chunks,
            "memory_suggestion": self._memory_suggestion(message, chunks),
        }

    def _answer_from_chunks(self, message: str, chunks: list[dict[str, object]]) -> str:
        if not chunks:
            return (
                "Aucun chunk RAG pertinent trouve. "
                "Je peux creer ou enrichir une note Markdown si cette information doit devenir durable."
            )

        citations = self._format_citations(chunks)
        return (
            "RAG verifie. Voici les sources les plus pertinentes pour traiter la demande: "
            f"{message}\n\nSources:\n{citations}"
        )

    def _format_citations(self, chunks: list[dict[str, object]]) -> str:
        lines = []
        seen = set()
        for chunk in chunks:
            path = str(chunk.get("path", "unknown.md"))
            line_start = chunk.get("line_start", "?")
            line_end = chunk.get("line_end", "?")
            key = (path, line_start, line_end)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {path}:{line_start}-{line_end}")
        return "\n".join(lines)

    def _memory_suggestion(self, message: str, chunks: list[dict[str, object]]) -> str | None:
        if chunks:
            return None
        if len(message.strip()) < 40:
            return None
        return "Information potentiellement nouvelle: proposer une note Markdown ou une injection memoire."
