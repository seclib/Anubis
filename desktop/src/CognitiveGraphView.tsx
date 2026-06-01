import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { BrainSnapshot, SkillGraph, openSkillUpdates, readSkillGraph } from "./api";

type CognitiveGraphViewProps = {
  snapshot: BrainSnapshot;
};

type NodeKind = "skill" | "agent" | "memory_cluster" | "system";

const NODE_TYPES: Array<"all" | NodeKind> = ["all", "skill", "agent", "memory_cluster", "system"];
const EDGE_TYPES = ["all", "depends_on", "member_of", "operates_on", "uses", "reports_to", "evolves_to"];

const NODE_COLORS: Record<NodeKind, string> = {
  skill: "#66d9c7",
  agent: "#8fb8ff",
  memory_cluster: "#f2c86b",
  system: "#d7a8ff"
};

function nodeLabel(id: string): string {
  return id.replace(/^skill:/, "").replace(/^agent:/, "").replace(/^memory:/, "").replace(/^system:/, "");
}

function compactText(text: string, limit = 260): string {
  return text.length > limit ? `${text.slice(0, limit - 1)}...` : text;
}

function buildElements(snapshot: BrainSnapshot, skillGraph: SkillGraph | null): cytoscape.ElementDefinition[] {
  const elements: cytoscape.ElementDefinition[] = [];
  const seenNodes = new Set<string>();
  const seenEdges = new Set<string>();

  function addNode(id: string, label: string, type: NodeKind, detail: string, extra: Record<string, unknown> = {}) {
    if (seenNodes.has(id)) return;
    seenNodes.add(id);
    elements.push({ data: { id, label, type, detail, ...extra } });
  }

  function addEdge(id: string, source: string, target: string, type: string, label: string) {
    if (seenEdges.has(id) || !seenNodes.has(source) || !seenNodes.has(target)) return;
    seenEdges.add(id);
    elements.push({ data: { id, source, target, type, label } });
  }

  addNode(
    "system:brain",
    "Anubis Brain",
    "system",
    `${snapshot.architecture.backend} · ${snapshot.architecture.live_updates}`
  );
  addNode("memory:vault", "Vault Memory", "memory_cluster", snapshot.memory.vault.path || "Markdown vault");
  addNode(
    "memory:embeddings",
    "Vector Memory",
    "memory_cluster",
    `${snapshot.memory.embeddings} embeddings · ${snapshot.memory.qdrant.collection || "Qdrant"}`
  );
  addNode("memory:skills", "Skill Memory", "memory_cluster", `${snapshot.memory.skills} skills tracked`);
  addNode("memory:chunks", "Chunk Memory", "memory_cluster", `${snapshot.memory.chunks} chunks from ${snapshot.memory.notes} notes`);

  addEdge("brain-vault", "system:brain", "memory:vault", "uses", "uses");
  addEdge("vault-embeddings", "memory:vault", "memory:embeddings", "uses", "indexed by");
  addEdge("vault-chunks", "memory:vault", "memory:chunks", "member_of", "split into");
  addEdge("skills-memory", "memory:skills", "system:brain", "reports_to", "informs");

  snapshot.agent_activity.active_agents.forEach((agent) => {
    const agentId = `agent:${agent.name}`;
    addNode(agentId, agent.name, "agent", `${agent.status} · ${agent.model}`, {
      role: agent.role,
      currentTask: agent.current_task
    });
    addEdge(`agent-${agent.name}-brain`, agentId, "system:brain", "reports_to", "reports");
    addEdge(`agent-${agent.name}-vault`, agentId, "memory:vault", "operates_on", "reads");
  });

  (skillGraph?.clusters || []).forEach((cluster) => {
    const clusterId = `memory:cluster:${cluster.id}`;
    addNode(
      clusterId,
      cluster.label || cluster.id,
      "memory_cluster",
      `${cluster.size} skills${cluster.average_fitness ? ` · fitness ${cluster.average_fitness.toFixed(2)}` : ""}`
    );
    addEdge(`cluster-${cluster.id}-skills`, clusterId, "memory:skills", "member_of", "groups");
  });

  (skillGraph?.nodes || []).forEach((skill) => {
    if (skill.type !== "skill") return;
    const skillId = `skill:${skill.id}`;
    addNode(skillId, skill.label || skill.id, "skill", compactText(skill.objective || skill.markdown || "Skill definition"), {
      status: skill.status,
      path: skill.path,
      fitness: skill.fitness
    });
    addEdge(`${skillId}-memory`, skillId, "memory:skills", "member_of", "stored in");
  });

  (skillGraph?.clusters || []).forEach((cluster) => {
    const clusterId = `memory:cluster:${cluster.id}`;
    cluster.members.forEach((member) => {
      addEdge(`cluster-${cluster.id}-${member}`, `skill:${member}`, clusterId, "member_of", "member");
    });
  });

  (skillGraph?.edges || []).forEach((edge) => {
    addEdge(`skill-edge:${edge.id}`, `skill:${edge.source}`, `skill:${edge.target}`, edge.type, edge.type.replaceAll("_", " "));
  });

  (skillGraph?.evolution_paths || []).forEach((path) => {
    path.path.forEach((source, index) => {
      const target = path.path[index + 1];
      if (target) addEdge(`evolution:${source}:${target}`, `skill:${source}`, `skill:${target}`, "evolves_to", "evolves");
    });
  });

  const primaryAgent = snapshot.agent_activity.active_agents[0]?.name;
  if (primaryAgent) {
    (skillGraph?.nodes || [])
      .filter((skill) => skill.type === "skill")
      .slice(0, 8)
      .forEach((skill) => {
        addEdge(`agent-skill:${primaryAgent}:${skill.id}`, `agent:${primaryAgent}`, `skill:${skill.id}`, "operates_on", "can invoke");
      });
  }

  return elements;
}

function selectedDetails(data: Record<string, unknown> | null): Record<string, unknown> {
  if (!data) return {};
  return {
    id: data.id,
    type: data.type,
    detail: data.detail,
    role: data.role,
    currentTask: data.currentTask,
    status: data.status,
    path: data.path,
    fitness: data.fitness
  };
}

export function CognitiveGraphView({ snapshot }: CognitiveGraphViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [skillGraph, setSkillGraph] = useState<SkillGraph | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | NodeKind>("all");
  const [edgeFilter, setEdgeFilter] = useState("all");
  const [liveStatus, setLiveStatus] = useState("Connecting");
  const [evolutionEvents, setEvolutionEvents] = useState<string[]>([]);

  useEffect(() => {
    let disposed = false;
    let pollTimer = 0;

    readSkillGraph()
      .then((graph) => {
        if (!disposed) setSkillGraph(graph);
      })
      .catch(() => setLiveStatus("Skill graph offline"));

    const close = openSkillUpdates(
      (graph) => {
        if (disposed) return;
        setSkillGraph(graph);
        setLiveStatus("Live");
        const added = graph.changes?.added_nodes || [];
        const changed = graph.changes?.changed_nodes || [];
        const removed = graph.changes?.removed_nodes || [];
        const nextEvents = [
          ...added.map((id) => `created ${id}`),
          ...changed.map((id) => `changed ${id}`),
          ...removed.map((id) => `removed ${id}`)
        ];
        if (nextEvents.length) setEvolutionEvents((current) => [...nextEvents, ...current].slice(0, 12));
      },
      () => {
        setLiveStatus("Polling");
        pollTimer = window.setInterval(() => {
          readSkillGraph().then(setSkillGraph).catch(() => setLiveStatus("Skill graph offline"));
        }, 3500);
      }
    );

    return () => {
      disposed = true;
      close();
      window.clearInterval(pollTimer);
    };
  }, []);

  const elements = useMemo(() => buildElements(snapshot, skillGraph), [skillGraph, snapshot]);
  const selectedData = useMemo(() => {
    const match = elements.find((element) => {
      const data = element.data as Record<string, unknown>;
      return data.id === selectedId && !("source" in data);
    });
    return (match?.data as Record<string, unknown>) || null;
  }, [selectedId, elements]);
  const details = selectedDetails(selectedData);
  const counts = useMemo(() => {
    const nodes = elements.filter((element) => {
      const data = element.data as Record<string, unknown>;
      return !("source" in data);
    });
    const edges = elements.length - nodes.length;
    return { nodes: nodes.length, edges };
  }, [elements]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const cy =
      cyRef.current ||
      cytoscape({
        container,
        minZoom: 0.35,
        maxZoom: 2.6,
        wheelSensitivity: 0.18,
        style: [
          {
            selector: "node",
            style: {
              "background-color": (element: cytoscape.NodeSingular) => NODE_COLORS[element.data("type") as NodeKind] || "#c6d2a3",
              "border-color": "#101316",
              "border-width": 2,
              color: "#edf2f6",
              "font-size": 11,
              label: "data(label)",
              "text-background-color": "#15181c",
              "text-background-opacity": 0.78,
              "text-background-padding": "3px",
              "text-margin-y": -8,
              "text-outline-color": "#15181c",
              "text-outline-width": 2,
              "text-wrap": "wrap",
              "text-max-width": 120,
              height: (element: cytoscape.NodeSingular) => (element.data("type") === "system" ? 42 : 30),
              width: (element: cytoscape.NodeSingular) => (element.data("type") === "system" ? 42 : 30)
            }
          },
          {
            selector: "node[type = 'skill']",
            style: { shape: "round-rectangle", width: 38, height: 24 }
          },
          {
            selector: "node[type = 'agent']",
            style: { shape: "hexagon" }
          },
          {
            selector: "node[type = 'memory_cluster']",
            style: { shape: "barrel" }
          },
          {
            selector: "edge",
            style: {
              "curve-style": "bezier",
              "target-arrow-shape": "triangle",
              "target-arrow-color": "#6f7780",
              "line-color": "#6f7780",
              "line-opacity": 0.62,
              width: 1.5,
              label: "data(label)",
              color: "#aeb7c0",
              "font-size": 9,
              "text-background-color": "#15181c",
              "text-background-opacity": 0.72,
              "text-background-padding": "2px"
            }
          },
          {
            selector: "edge[type = 'evolves_to']",
            style: { "line-color": "#f2c86b", "target-arrow-color": "#f2c86b", "line-style": "dashed", width: 2.5 }
          },
          {
            selector: "edge[type = 'depends_on']",
            style: { "line-color": "#8fb8ff", "target-arrow-color": "#8fb8ff" }
          },
          {
            selector: "edge[type = 'member_of']",
            style: { "line-color": "#66d9c7", "target-arrow-color": "#66d9c7" }
          },
          {
            selector: ".dimmed",
            style: { opacity: 0.12 }
          },
          {
            selector: ".selected",
            style: { "border-color": "#ffffff", "border-width": 4, "line-opacity": 1, opacity: 1 }
          }
        ],
        elements: []
    });

    cyRef.current = cy;
    cy.off("tap");
    cy.on("tap", "node", (event) => setSelectedId(event.target.id()));
    cy.on("tap", (event) => {
      if (event.target === cy) setSelectedId("");
    });

    return () => {
      cy.off("tap");
    };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      cy.elements().remove();
      cy.add(elements);
    });

    const layout = cy.layout({
      name: "cose",
      animate: false,
      fit: true,
      padding: 32,
      nodeRepulsion: 6500,
      idealEdgeLength: 115,
      componentSpacing: 90
    });
    layout.run();
  }, [elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.elements().removeClass("dimmed selected");
    const visibleNodes =
      typeFilter === "all" ? cy.nodes() : cy.nodes().filter((node) => node.data("type") === typeFilter);
    const visibleEdges =
      edgeFilter === "all" ? cy.edges() : cy.edges().filter((edge) => edge.data("type") === edgeFilter);
    cy.elements().addClass("dimmed");
    visibleNodes.removeClass("dimmed");
    visibleEdges
      .filter((edge) => !edge.source().hasClass("dimmed") && !edge.target().hasClass("dimmed"))
      .removeClass("dimmed");
    if (selectedId) {
      const selected = cy.getElementById(selectedId);
      selected.removeClass("dimmed").addClass("selected");
      selected.connectedEdges().removeClass("dimmed").addClass("selected");
      selected.neighborhood("node").removeClass("dimmed");
    }
  }, [edgeFilter, elements, selectedId, typeFilter]);

  return (
    <section className="brain-panel cognitive-graph-panel">
      <header>
        <div>
          <h2>Cognitive Graph</h2>
          <span>
            {counts.nodes} nodes · {counts.edges} relationships · {liveStatus}
          </span>
        </div>
        <div className="cognitive-controls">
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as "all" | NodeKind)} aria-label="Filter cognitive graph nodes">
            {NODE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type === "all" ? "All nodes" : type.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <select value={edgeFilter} onChange={(event) => setEdgeFilter(event.target.value)} aria-label="Filter cognitive graph relationships">
            {EDGE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type === "all" ? "All relationships" : type.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="cognitive-layout">
        <div className="cognitive-canvas" ref={containerRef} />
        <aside className="cognitive-inspector">
          <section>
            <h3>{selectedData ? nodeLabel(String(selectedData.id)) : "Node Inspection"}</h3>
            {selectedData ? (
              <>
                {Object.entries(details)
                  .filter(([, value]) => value !== undefined && value !== "")
                  .map(([key, value]) => (
                    <p key={key}>
                      <span>{key.replaceAll("_", " ")}</span>
                      <strong>{typeof value === "object" ? JSON.stringify(value) : String(value)}</strong>
                    </p>
                  ))}
              </>
            ) : (
              <p>
                <span>selection</span>
                <strong>Select any node to inspect status, memory role, skill metadata, or agent activity.</strong>
              </p>
            )}
          </section>
          <section>
            <h3>Evolution Tracking</h3>
            {evolutionEvents.length ? (
              evolutionEvents.map((event) => <p key={event}><span>event</span><strong>{event}</strong></p>)
            ) : skillGraph?.evolution_paths?.length ? (
              skillGraph.evolution_paths.slice(0, 6).map((path) => (
                <p key={`${path.root}-${path.length}`}>
                  <span>{path.root}</span>
                  <strong>{path.path.join(" -> ")}</strong>
                </p>
              ))
            ) : (
              <p>
                <span>state</span>
                <strong>No evolution events observed yet.</strong>
              </p>
            )}
          </section>
        </aside>
      </div>
    </section>
  );
}
