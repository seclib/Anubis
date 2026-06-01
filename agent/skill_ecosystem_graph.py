"""Living skill ecosystem graph engine for Anubis."""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

NODE_TYPES = {"skill", "agent", "memory_chunk", "task", "knowledge_cluster"}
EDGE_TYPES = {
    "depends_on",
    "enhances",
    "derived_from",
    "conflicts_with",
    "triggers",
    "merges_into",
}

DEFAULT_SKILLS_DIR = Path(".agents/skills")
DNA_REGISTRY_FILE = "skill-dna-registry.json"
EVOLUTION_TREE_FILE = "evolution-tree.md"
SKILL_TOKEN_RE = re.compile(r"`([^`]+)`")
AGENT_RE = re.compile(r"\b([a-z][a-z0-9_-]*_agent)\b")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    raw = parts[1]
    result: dict[str, Any] = {}
    current_key = ""
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            result.setdefault(current_key, []).append(line.split("  - ", 1)[1].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        result[current_key] = [] if value == "" else value
    return result


def _load_dna_registry(skills_dir: Path) -> dict[str, dict[str, Any]]:
    path = skills_dir / DNA_REGISTRY_FILE
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    genomes = payload.get("genomes", [])
    if not isinstance(genomes, list):
        return {}
    return {
        str(genome.get("id")): genome
        for genome in genomes
        if isinstance(genome, dict) and str(genome.get("id", "")).strip()
    }


def _skill_markdown_files(skills_dir: Path) -> list[Path]:
    if not skills_dir.exists():
        return []
    return sorted(
        path
        for path in skills_dir.glob("*.md")
        if path.name not in {EVOLUTION_TREE_FILE} and not path.name.startswith("system-cognition-report")
    )


def _skill_id_from_file(path: Path, text: str) -> str:
    frontmatter = _parse_frontmatter(text)
    return str(frontmatter.get("name") or path.stem).strip()


def _tokens_for(value: str) -> set[str]:
    stop = {
        "agent",
        "skill",
        "engine",
        "system",
        "anubis",
        "with",
        "from",
        "into",
        "when",
        "this",
        "that",
        "should",
        "needs",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in stop
    }


def _add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    node_id = str(node["id"])
    existing = nodes.get(node_id, {})
    merged = {**existing, **node}
    if node.get("type") == "skill" and node.get("path") and merged.get("status") == "referenced_missing":
        merged.pop("status", None)
    merged["type"] = merged.get("type", "skill")
    nodes[node_id] = merged


def _edge_id(source: str, target: str, edge_type: str) -> str:
    return f"{source}->{edge_type}->{target}"


def _add_edge(
    edges: dict[str, dict[str, Any]],
    source: str,
    target: str,
    edge_type: str,
    *,
    weight: float = 1.0,
    evidence: str = "",
) -> None:
    if not source or not target or edge_type not in EDGE_TYPES:
        return
    edge = {
        "id": _edge_id(source, target, edge_type),
        "source": source,
        "target": target,
        "type": edge_type,
        "weight": round(float(weight), 3),
    }
    if evidence:
        edge["evidence"] = evidence
    edges[edge["id"]] = edge


def _parse_markdown_skill(path: Path, dna: dict[str, dict[str, Any]]) -> dict[str, Any]:
    text = _read_text(path)
    frontmatter = _parse_frontmatter(text)
    skill_id = _skill_id_from_file(path, text)
    genome = dna.get(skill_id, {})
    dependencies = frontmatter.get("dependencies", [])
    if not isinstance(dependencies, list):
        dependencies = []
    objective = str(frontmatter.get("objective") or genome.get("purpose") or "").strip()
    fitness = genome.get("fitness_score", {})
    if not isinstance(fitness, dict):
        fitness = {}
    triggers = genome.get("triggers", [])
    if not isinstance(triggers, list):
        triggers = []
    mutation_rules = genome.get("mutation_rules", [])
    if not isinstance(mutation_rules, list):
        mutation_rules = []
    return {
        "id": skill_id,
        "type": "skill",
        "label": str(genome.get("name") or skill_id).strip(),
        "path": str(path),
        "objective": objective,
        "dependencies": [str(item).strip() for item in dependencies if str(item).strip()],
        "triggers": [str(item).strip() for item in triggers if str(item).strip()],
        "mutation_rules": [str(item).strip() for item in mutation_rules if str(item).strip()],
        "fitness": fitness,
        "content_tokens": sorted(_tokens_for(text + " " + objective)),
    }


def _parse_evolution_tree(skills_dir: Path) -> tuple[list[tuple[str, str]], list[tuple[list[str], str]]]:
    text = _read_text(skills_dir / EVOLUTION_TREE_FILE)
    chains: list[tuple[str, str]] = []
    merges: list[tuple[list[str], str]] = []
    for raw in SKILL_TOKEN_RE.findall(text):
        if "->" not in raw:
            continue
        left, right = raw.rsplit("->", 1)
        target = right.strip()
        if "+" in left:
            sources = [part.strip() for part in left.split("+") if part.strip()]
            if sources and target:
                merges.append((sources, target))
            continue
        parts = [part.strip() for part in raw.split("->") if part.strip()]
        chains.extend((parts[index], parts[index + 1]) for index in range(len(parts) - 1))
    return chains, merges


def build_skill_ecosystem_graph(skills_dir: str | Path = DEFAULT_SKILLS_DIR) -> dict[str, Any]:
    """Build nodes, edges, clusters, evolution paths, insights, and visual exports."""
    root = Path(skills_dir)
    dna = _load_dna_registry(root)
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    skills = [_parse_markdown_skill(path, dna) for path in _skill_markdown_files(root)]
    for skill in skills:
        _add_node(nodes, skill)
        for dependency in skill["dependencies"]:
            if dependency not in nodes:
                _add_node(
                    nodes,
                    {
                        "id": dependency,
                        "type": "skill",
                        "label": dependency,
                        "status": "referenced_missing" if dependency not in dna else "referenced",
                    },
                )
            _add_edge(edges, skill["id"], dependency, "depends_on", evidence="frontmatter.dependencies")

        for trigger in skill["triggers"]:
            task_id = f"task:{_slug(trigger)}"
            _add_node(nodes, {"id": task_id, "type": "task", "label": trigger})
            _add_edge(edges, task_id, skill["id"], "triggers", weight=0.8, evidence="skill_dna.triggers")

        for agent in sorted(set(AGENT_RE.findall(_read_text(Path(skill["path"]))))):
            _add_node(nodes, {"id": agent, "type": "agent", "label": agent})
            _add_edge(edges, skill["id"], agent, "enhances", weight=0.6, evidence="agent mention")

    chains, merges = _parse_evolution_tree(root)
    for source, target in chains:
        if source not in nodes:
            _add_node(nodes, {"id": source, "type": "skill", "label": source, "status": "evolution_only"})
        if target not in nodes:
            _add_node(nodes, {"id": target, "type": "skill", "label": target, "status": "evolution_only"})
        _add_edge(edges, source, target, "derived_from", weight=0.9, evidence=EVOLUTION_TREE_FILE)
    for sources, target in merges:
        if target not in nodes:
            _add_node(nodes, {"id": target, "type": "skill", "label": target, "status": "evolution_only"})
        for source in sources:
            if source not in nodes:
                _add_node(nodes, {"id": source, "type": "skill", "label": source, "status": "evolution_only"})
            _add_edge(edges, source, target, "merges_into", weight=0.95, evidence=EVOLUTION_TREE_FILE)

    clusters = cluster_skill_ecosystem(nodes, edges)
    evolution_paths = build_evolution_paths(nodes, edges)
    insights = generate_skill_ecosystem_insights(nodes, edges, clusters)

    graph = {
        "nodes": sorted(nodes.values(), key=lambda node: (node["type"], node["id"])),
        "edges": sorted(edges.values(), key=lambda edge: (edge["type"], edge["source"], edge["target"])),
        "clusters": clusters,
        "evolution_paths": evolution_paths,
        "insights": insights,
    }
    graph["visual"] = {
        "d3": to_d3_graph(graph),
        "cytoscape": to_cytoscape_graph(graph),
        "neo4j": to_neo4j_statements(graph),
    }
    return graph


def update_skill_ecosystem_graph(
    previous_graph: dict[str, Any] | None = None,
    skills_dir: str | Path = DEFAULT_SKILLS_DIR,
) -> dict[str, Any]:
    """Rebuild the graph and report added, removed, and changed graph elements."""
    graph = build_skill_ecosystem_graph(skills_dir)
    previous_graph = previous_graph or {"nodes": [], "edges": []}
    old_nodes = {node["id"]: node for node in previous_graph.get("nodes", []) if isinstance(node, dict)}
    new_nodes = {node["id"]: node for node in graph["nodes"]}
    old_edges = {edge["id"]: edge for edge in previous_graph.get("edges", []) if isinstance(edge, dict)}
    new_edges = {edge["id"]: edge for edge in graph["edges"]}
    graph["changes"] = {
        "added_nodes": sorted(set(new_nodes) - set(old_nodes)),
        "removed_nodes": sorted(set(old_nodes) - set(new_nodes)),
        "added_edges": sorted(set(new_edges) - set(old_edges)),
        "removed_edges": sorted(set(old_edges) - set(new_edges)),
        "changed_nodes": sorted(
            node_id
            for node_id in set(new_nodes) & set(old_nodes)
            if new_nodes[node_id] != old_nodes[node_id]
        ),
    }
    return graph


def _similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_tokens = set(left.get("content_tokens", [])) | _tokens_for(str(left.get("label", "")))
    right_tokens = set(right.get("content_tokens", [])) | _tokens_for(str(right.get("label", "")))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def cluster_skill_ecosystem(
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
    *,
    similarity_threshold: float = 0.16,
) -> list[dict[str, Any]]:
    """Group related skills into capability families."""
    skill_nodes = {node_id: node for node_id, node in nodes.items() if node.get("type") == "skill"}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges.values():
        if edge["source"] in skill_nodes and edge["target"] in skill_nodes:
            adjacency[edge["source"]].add(edge["target"])
            adjacency[edge["target"]].add(edge["source"])
    skill_ids = sorted(skill_nodes)
    for index, left_id in enumerate(skill_ids):
        for right_id in skill_ids[index + 1 :]:
            if _similarity(skill_nodes[left_id], skill_nodes[right_id]) >= similarity_threshold:
                adjacency[left_id].add(right_id)
                adjacency[right_id].add(left_id)

    seen: set[str] = set()
    clusters: list[dict[str, Any]] = []
    for skill_id in skill_ids:
        if skill_id in seen:
            continue
        queue = deque([skill_id])
        members: list[str] = []
        seen.add(skill_id)
        while queue:
            current = queue.popleft()
            members.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        tokens: set[str] = set()
        fitness_values: list[float] = []
        for member in members:
            node = skill_nodes[member]
            tokens.update(set(node.get("content_tokens", [])))
            overall = node.get("fitness", {}).get("overall")
            if isinstance(overall, int | float):
                fitness_values.append(float(overall))
        label = _cluster_label(tokens, members)
        clusters.append(
            {
                "id": f"cluster:{_slug(label or members[0])}",
                "type": "knowledge_cluster",
                "label": label,
                "members": sorted(members),
                "size": len(members),
                "average_fitness": round(sum(fitness_values) / len(fitness_values), 3)
                if fitness_values
                else 0.0,
            }
        )
    return sorted(clusters, key=lambda item: (-item["size"], item["label"]))


def _cluster_label(tokens: set[str], members: list[str]) -> str:
    priority = [
        "retrieval",
        "memory",
        "writing",
        "cognition",
        "evolution",
        "compression",
        "documentation",
        "reasoning",
        "executor",
        "optimizer",
    ]
    selected = [token for token in priority if token in tokens]
    if not selected:
        selected = sorted(tokens)[:2] or [members[0]]
    return " / ".join(selected[:3])


def build_evolution_paths(
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build lineage paths from derived_from and merges_into edges."""
    lineage_edges = [
        edge
        for edge in edges.values()
        if edge.get("type") in {"derived_from", "merges_into"}
        and nodes.get(edge["source"], {}).get("type") == "skill"
        and nodes.get(edge["target"], {}).get("type") == "skill"
    ]
    incoming = defaultdict(int)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in lineage_edges:
        outgoing[edge["source"]].append(edge["target"])
        incoming[edge["target"]] += 1
    roots = sorted({edge["source"] for edge in lineage_edges if incoming[edge["source"]] == 0})
    if not roots:
        roots = sorted({edge["source"] for edge in lineage_edges})
    paths: list[dict[str, Any]] = []
    for root in roots:
        stack = [(root, [root])]
        while stack:
            current, path = stack.pop()
            children = sorted(set(outgoing.get(current, [])) - set(path))
            if not children:
                if len(path) > 1:
                    paths.append({"root": root, "path": path, "length": len(path)})
                continue
            for child in reversed(children):
                stack.append((child, path + [child]))
    return sorted(paths, key=lambda item: (-item["length"], item["path"]))


def generate_skill_ecosystem_insights(
    nodes: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, Any]],
    clusters: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate operational graph insights for skill maintenance."""
    degree = defaultdict(int)
    incoming = defaultdict(int)
    for edge in edges.values():
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
        incoming[edge["target"]] += 1

    skills = [node for node in nodes.values() if node.get("type") == "skill"]
    most_used = sorted(
        (
            {
                "id": node["id"],
                "usage_frequency": float(node.get("fitness", {}).get("usage_frequency", 0.0) or 0.0),
                "overall": float(node.get("fitness", {}).get("overall", 0.0) or 0.0),
            }
            for node in skills
        ),
        key=lambda item: (-item["usage_frequency"], -item["overall"], item["id"]),
    )[:8]
    isolated = sorted(node["id"] for node in skills if degree[node["id"]] == 0)
    weak_dependencies = sorted(
        {
            edge["target"]
            for edge in edges.values()
            if edge["type"] == "depends_on"
            and nodes.get(edge["target"], {}).get("status") == "referenced_missing"
        }
    )
    critical_clusters = [
        cluster
        for cluster in clusters
        if cluster["size"] >= 3 or cluster["average_fitness"] >= 0.85
    ]
    central_skills = sorted(
        (
            {"id": node["id"], "degree": degree[node["id"]], "incoming": incoming[node["id"]]}
            for node in skills
            if degree[node["id"]]
        ),
        key=lambda item: (-item["degree"], -item["incoming"], item["id"]),
    )[:8]

    return {
        "most_used_skills": most_used,
        "isolated_skills": isolated,
        "critical_clusters": critical_clusters,
        "weak_dependencies": weak_dependencies,
        "central_skills": central_skills,
    }


def to_d3_graph(graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": node["id"],
                "type": node["type"],
                "label": node.get("label", node["id"]),
                "fitness": node.get("fitness", {}),
            }
            for node in graph.get("nodes", [])
        ],
        "links": [
            {
                "source": edge["source"],
                "target": edge["target"],
                "type": edge["type"],
                "weight": edge.get("weight", 1.0),
            }
            for edge in graph.get("edges", [])
        ],
    }


def to_cytoscape_graph(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "elements": [
            {"data": {"id": node["id"], "label": node.get("label", node["id"]), "type": node["type"]}}
            for node in graph.get("nodes", [])
        ]
        + [
            {
                "data": {
                    "id": edge["id"],
                    "source": edge["source"],
                    "target": edge["target"],
                    "type": edge["type"],
                    "weight": edge.get("weight", 1.0),
                }
            }
            for edge in graph.get("edges", [])
        ]
    }


def to_neo4j_statements(graph: dict[str, Any]) -> list[str]:
    statements: list[str] = []
    for node in graph.get("nodes", []):
        label = str(node["type"]).title().replace("_", "")
        statements.append(
            "MERGE (n:%s {id: %s}) SET n.label = %s"
            % (label, json.dumps(node["id"]), json.dumps(node.get("label", node["id"])))
        )
    for edge in graph.get("edges", []):
        relation = str(edge["type"]).upper()
        statements.append(
            "MATCH (a {id: %s}), (b {id: %s}) MERGE (a)-[r:%s]->(b) SET r.weight = %s"
            % (
                json.dumps(edge["source"]),
                json.dumps(edge["target"]),
                relation,
                json.dumps(edge.get("weight", 1.0)),
            )
        )
    return statements


__all__ = [
    "EDGE_TYPES",
    "NODE_TYPES",
    "build_evolution_paths",
    "build_skill_ecosystem_graph",
    "cluster_skill_ecosystem",
    "generate_skill_ecosystem_insights",
    "to_cytoscape_graph",
    "to_d3_graph",
    "to_neo4j_statements",
    "update_skill_ecosystem_graph",
]
