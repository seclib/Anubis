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
                "I could not find anything relevant in your workspace yet. "
                "Add a note or import a document and I will use it automatically."
            )

        snippets = self._format_snippets(chunks)
        return (
            "I found relevant workspace context for your question: "
            f"{message}\n\n{snippets}"
        )

    def _format_snippets(self, chunks: list[dict[str, object]]) -> str:
        lines = []
        seen = set()
        for chunk in chunks:
            path = str(chunk.get("path", "unknown.md"))
            text = str(chunk.get("text", "")).strip()
            key = (path, text)
            if key in seen:
                continue
            seen.add(key)
            preview = text[:220] + ("..." if len(text) > 220 else "")
            lines.append(f"- {preview}")
        return "\n".join(lines)

    def _memory_suggestion(self, message: str, chunks: list[dict[str, object]]) -> str | None:
        if chunks:
            return None
        if len(message.strip()) < 40:
            return None
        return "This may be new information worth saving as a note."
