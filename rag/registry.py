from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable


class RagRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RagModuleSpec:
    name: str
    package: str
    description: str
    components: dict[str, str] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()

    def load_component(self, component: str) -> type[Any]:
        target = self.components.get(component)
        if not target:
            raise RagRegistryError(f"Component '{component}' is not registered for RAG module '{self.name}'")
        module_path, _, attr = target.partition(":")
        if not module_path or not attr:
            raise RagRegistryError(f"Invalid component target '{target}' for RAG module '{self.name}'")
        module = importlib.import_module(module_path)
        try:
            loaded = getattr(module, attr)
        except AttributeError as exc:
            raise RagRegistryError(f"Component '{attr}' not found in '{module_path}'") from exc
        return loaded

    def create(self, component: str = "ingestion", *args: Any, **kwargs: Any) -> Any:
        cls = self.load_component(component)
        return cls(*args, **kwargs)


class RagRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, RagModuleSpec] = {}
        self._aliases: dict[str, str] = {}

    def register(self, spec: RagModuleSpec) -> None:
        if spec.name in self._modules:
            raise RagRegistryError(f"RAG module '{spec.name}' is already registered")
        self._modules[spec.name] = spec
        self._aliases[spec.name] = spec.name
        for alias in spec.aliases:
            self._aliases[alias] = spec.name

    def get(self, name: str) -> RagModuleSpec:
        canonical = self._aliases.get(name)
        if not canonical:
            raise RagRegistryError(f"Unknown RAG module '{name}'")
        return self._modules[canonical]

    def has(self, name: str) -> bool:
        return name in self._aliases

    def names(self) -> list[str]:
        return sorted(self._modules)

    def specs(self) -> list[RagModuleSpec]:
        return [self._modules[name] for name in self.names()]

    def load(self, name: str, component: str) -> type[Any]:
        return self.get(name).load_component(component)

    def create(self, name: str, component: str = "ingestion", *args: Any, **kwargs: Any) -> Any:
        return self.get(name).create(component, *args, **kwargs)

    def component_map(self) -> dict[str, dict[str, str]]:
        return {name: dict(spec.components) for name, spec in self._modules.items()}


def _build_registry() -> RagRegistry:
    registry = RagRegistry()
    for spec in (
        RagModuleSpec(
            name="osint",
            package="rag.osint",
            description="OSINT entity and source intelligence RAG",
            components={
                "ingestion": "rag.osint.ingestion:OsintIngestion",
                "processor": "rag.osint.processor:OsintProcessor",
                "schema_document": "rag.osint.schema:OsintDocument",
                "schema_chunk": "rag.osint.schema:OsintChunk",
                "embedding": "rag.shared.embedding:EmbeddingPipeline",
            },
        ),
        RagModuleSpec(
            name="cve",
            package="rag.cve",
            description="CVE, NVD, MITRE, and CISA KEV vulnerability RAG",
            components={
                "ingestion": "rag.cve.cve_ingestion:CveIngestion",
                "parser": "rag.cve.cve_parser:CveParser",
                "schema_record": "rag.cve.schema:CveRecord",
                "schema_chunk": "rag.cve.schema:CveChunk",
                "embedding": "rag.cve.cve_embeddings:CveEmbeddingPipeline",
            },
        ),
        RagModuleSpec(
            name="bugbounty",
            package="rag.bugbounty",
            description="Bug bounty report, payload, and bypass technique RAG",
            aliases=("bug_bounty",),
            components={
                "ingestion": "rag.bugbounty.ingestion:BugBountyIngestion",
                "parser": "rag.bugbounty.report_parser:BugBountyReportParser",
                "payload_indexer": "rag.bugbounty.payload_indexer:PayloadIndexer",
                "schema_report": "rag.bugbounty.schema:BugBountyReport",
                "schema_chunk": "rag.bugbounty.schema:BugBountyChunk",
                "embedding": "rag.shared.embedding:EmbeddingPipeline",
            },
        ),
        RagModuleSpec(
            name="dev",
            package="rag.dev",
            description="Repository code, StackOverflow, and error-fix RAG",
            aliases=("code", "coding"),
            components={
                "ingestion": "rag.dev.repo_ingestion:DevRagIngestion",
                "code_indexer": "rag.dev.code_indexer:CodeIndexer",
                "stackoverflow_loader": "rag.dev.stackoverflow_loader:StackOverflowLoader",
                "schema_document": "rag.dev.schema:CodeDocument",
                "schema_chunk": "rag.dev.schema:CodeChunk",
                "embedding": "rag.shared.embedding:EmbeddingPipeline",
            },
        ),
        RagModuleSpec(
            name="defense",
            package="rag.defense",
            description="Cyber defense, MITRE ATT&CK, IDS rules, and playbook RAG",
            aliases=("cyberdefense", "cyber_defense"),
            components={
                "ingestion": "rag.defense.defense_ingestion:DefenseIngestion",
                "mitre_parser": "rag.defense.mitre_parser:MitreAttackParser",
                "rules_indexer": "rag.defense.rules_indexer:IdsRulesIndexer",
                "schema_technique": "rag.defense.schema:AttackTechnique",
                "schema_rule": "rag.defense.schema:DetectionRule",
                "schema_playbook": "rag.defense.schema:DefensePlaybook",
                "schema_chunk": "rag.defense.schema:DefenseChunk",
                "embedding": "rag.shared.embedding:EmbeddingPipeline",
            },
        ),
        RagModuleSpec(
            name="tools",
            package="rag.tools",
            description="Offensive security tooling templates and workflow RAG",
            aliases=("tooling",),
            components={
                "ingestion": "rag.tools.tool_indexer:ToolIndexer",
                "tool_indexer": "rag.tools.tool_indexer:ToolIndexer",
                "template_library": "rag.tools.command_templates:CommandTemplateLibrary",
                "workflow_builder": "rag.tools.workflow_builder:WorkflowBuilder",
                "schema_scenario": "rag.tools.schema:ToolUsageScenario",
                "schema_chunk": "rag.tools.schema:ToolChunk",
                "embedding": "rag.shared.embedding:EmbeddingPipeline",
            },
        ),
        RagModuleSpec(
            name="discovery",
            package="rag.discovery",
            description="Search intelligence patterns for GHDB, dorks, Shodan, Censys, and FOFA",
            aliases=("dorks", "search_intel"),
            components={
                "ingestion": "rag.discovery.ingestion:DiscoveryIngestion",
                "parser": "rag.discovery.parser:DiscoveryParser",
                "search_engine": "rag.discovery.search_engine:DiscoverySearchEngine",
                "schema_entry": "rag.discovery.schema:DiscoveryEntry",
                "schema_chunk": "rag.discovery.schema:DiscoveryChunk",
                "embedding": "rag.discovery.embedding:DiscoveryEmbeddingPipeline",
            },
        ),
        RagModuleSpec(
            name="graph",
            package="rag.graph",
            description="Neo4j graph RAG for OSINT and threat intelligence relationships",
            components={
                "ingestion": "rag.graph.graph_builder:GraphBuilder",
                "builder": "rag.graph.graph_builder:GraphBuilder",
                "client": "rag.graph.neo4j_client:Neo4jClient",
                "mapper": "rag.graph.relationship_mapper:RelationshipMapper",
                "query_engine": "rag.graph.query_engine:GraphQueryEngine",
            },
        ),
        RagModuleSpec(
            name="memory",
            package="rag.memory",
            description="Persistent semantic memory RAG for sessions and investigations",
            components={
                "ingestion": "rag.memory.memory_indexer:MemoryIndexer",
                "indexer": "rag.memory.memory_indexer:MemoryIndexer",
                "store": "rag.memory.memory_store:MemoryStore",
                "session_tracker": "rag.memory.session_tracker:SessionTracker",
                "schema_record": "rag.memory.memory_store:MemoryRecord",
                "schema_chunk": "rag.memory.memory_store:MemoryChunk",
                "embedding": "rag.shared.embedding:EmbeddingPipeline",
            },
        ),
    ):
        registry.register(spec)
    return registry


registry = _build_registry()


def get_registry() -> RagRegistry:
    return registry


def get_rag_module(name: str) -> RagModuleSpec:
    return registry.get(name)


def load_component(module_name: str, component: str) -> type[Any]:
    return registry.load(module_name, component)


def create_component(module_name: str, component: str = "ingestion", *args: Any, **kwargs: Any) -> Any:
    return registry.create(module_name, component, *args, **kwargs)


def registered_modules() -> list[str]:
    return registry.names()
