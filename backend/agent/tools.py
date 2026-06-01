from backend.rag.retriever import RagRetriever
from backend.rag.embedder import LocalEmbedder
from backend.rag.indexer import RagIndexer
from backend.vault.service import VaultService
from backend.tools.sandbox import SandboxExecutor, ToolRequest


class AgentTools:
    def __init__(self) -> None:
        self.vault = VaultService()
        self.rag = RagRetriever()
        self.embedder = LocalEmbedder()
        self.indexer = RagIndexer()
        self.sandbox = SandboxExecutor()

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
        self.update_note(path, patch)

    def update_note(self, path: str, patch: str) -> None:
        content = self.vault.read_note(path)
        self.vault.write_note(path, f"{content.rstrip()}\n\n{patch.strip()}\n")

    def embed(self, text: str) -> list[float]:
        return self.embedder.embed(text)

    def reindex_memory(self) -> int:
        return self.indexer.reindex_all()

    def execute(self, tool: str, args: dict[str, object]) -> object:
        if tool in {"search", "rag_query", "search_rag"}:
            return self.search_rag(str(args.get("query", "")))
        if tool in {"read", "read_note"}:
            return self.read_note(str(args["path"]))
        if tool in {"write", "write_note"}:
            self.write_note(str(args["path"]), str(args.get("content", "")))
            return {"status": "written", "path": str(args["path"])}
        if tool in {"update", "update_note"}:
            self.update_note(str(args["path"]), str(args.get("patch", "")))
            return {"status": "updated", "path": str(args["path"])}
        if tool == "reindex_memory":
            return {"status": "indexed", "chunks": self.reindex_memory()}
        if tool == "shell":
            request = ToolRequest(
                command=str(args.get("command", "")),
                justification=str(args.get("justification", "")),
                cwd=str(args.get("cwd", ".")),
                allow_network=bool(args.get("allow_network", False)),
            )
            return self.sandbox.execute(request).__dict__
        raise ValueError(f"Tool not allowed: {tool}")
