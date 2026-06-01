from backend.rag.retriever import RagRetriever
from backend.rag.embedder import LocalEmbedder
from backend.vault.service import VaultService


class AgentTools:
    def __init__(self) -> None:
        self.vault = VaultService()
        self.rag = RagRetriever()
        self.embedder = LocalEmbedder()

    def search(self, query: str) -> list[dict[str, object]]:
        return self.search_rag(query)

    def rag_query(self, query: str) -> list[dict[str, object]]:
        return self.search_rag(query)

    def search_rag(self, query: str) -> list[dict[str, object]]:
        return self.rag.search(query)

    def read(self, path: str) -> str:
        return self.read_note(path)

    def read_note(self, path: str) -> str:
        return self.vault.read_note(path)

    def write(self, path: str, content: str) -> None:
        self.write_note(path, content)

    def write_note(self, path: str, content: str) -> None:
        self.vault.write_note(path, content)

    def update(self, path: str, patch: str) -> None:
        content = self.vault.read_note(path)
        self.vault.write_note(path, f"{content.rstrip()}\n\n{patch.strip()}\n")

    def embed(self, text: str) -> list[float]:
        return self.embedder.embed(text)
