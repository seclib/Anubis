import React, { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import { openSkillUpdates, readSkillGraph, SkillCluster, SkillEdge, SkillGraph, SkillNode } from "./api";

type GraphNode = SkillNode & d3.SimulationNodeDatum;
type GraphLink = d3.SimulationLinkDatum<GraphNode> & Omit<SkillEdge, "source" | "target">;

const EDGE_TYPES = ["depends_on", "enhances", "merges_into", "conflicts_with", "derived_from"];
const NODE_COLORS: Record<string, string> = {
  skill: "#66d9c7",
  agent: "#8fb8ff",
  task: "#f2c86b",
  knowledge_cluster: "#d7a8ff",
  memory_chunk: "#ff9f8a"
};

function endpointId(value: string | number | SkillNode | GraphNode): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : value.id;
}

function formatEdge(edge: SkillEdge): string {
  return edge.type.replaceAll("_", " ");
}

function markdownPreview(markdown: string): string {
  return markdown
    .replace(/^---[\s\S]*?---/, "")
    .replace(/```[\s\S]*?```/g, "[code block]")
    .replace(/[#*_>`-]/g, "")
    .trim();
}

function MetricList({
  title,
  children,
  empty
}: {
  title: string;
  children: React.ReactNode;
  empty: string;
}) {
  const hasChildren = React.Children.count(children) > 0;
  return (
    <section className="skill-metric">
      <h3>{title}</h3>
      <div>{hasChildren ? children : <p className="empty">{empty}</p>}</div>
    </section>
  );
}

export function SkillGraphView() {
  const [graph, setGraph] = useState<SkillGraph | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [hoveredId, setHoveredId] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [edgeFilter, setEdgeFilter] = useState("all");
  const [liveStatus, setLiveStatus] = useState("Connecting");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let disposed = false;
    let pollTimer = 0;

    readSkillGraph()
      .then((payload) => {
        if (!disposed) {
          setGraph(payload);
          setSelectedId((current) => current || payload.nodes.find((node) => node.type === "skill")?.id || "");
        }
      })
      .catch(() => setLiveStatus("Offline"));

    const startPolling = () => {
      if (pollTimer) return;
      setLiveStatus("Polling");
      pollTimer = window.setInterval(() => {
        readSkillGraph().then(setGraph).catch(() => setLiveStatus("Offline"));
      }, 3500);
    };

    const closeEvents = openSkillUpdates(
      (payload) => {
        if (!disposed) {
          setGraph(payload);
          setLiveStatus(payload.changes ? "Live update received" : "Live");
        }
      },
      startPolling
    );

    return () => {
      disposed = true;
      closeEvents();
      window.clearInterval(pollTimer);
    };
  }, []);

  const visibleGraph = useMemo(() => {
    if (!graph) return { nodes: [], links: [] };
    const nodes = graph.nodes.filter((node) => typeFilter === "all" || node.type === typeFilter);
    const nodeIds = new Set(nodes.map((node) => node.id));
    const links = graph.edges.filter(
      (edge) =>
        nodeIds.has(edge.source) &&
        nodeIds.has(edge.target) &&
        (edgeFilter === "all" || edge.type === edgeFilter)
    );
    return { nodes, links };
  }, [edgeFilter, graph, typeFilter]);

  const selectedNode = useMemo(
    () => graph?.nodes.find((node) => node.id === selectedId) || null,
    [graph, selectedId]
  );

  const hoverDependencies = useMemo(() => {
    if (!graph || !hoveredId) return [];
    return graph.edges
      .filter((edge) => edge.source === hoveredId || edge.target === hoveredId)
      .map((edge) => `${edge.source === hoveredId ? edge.target : edge.source} · ${formatEdge(edge)}`)
      .slice(0, 8);
  }, [graph, hoveredId]);

  const newlyCreated =
    graph?.changes?.added_nodes?.filter((id) => graph.nodes.some((node) => node.id === id && node.type === "skill")) || [];
  const allTypes = useMemo(() => ["all", ...Array.from(new Set(graph?.nodes.map((node) => node.type) || [])).sort()], [graph]);
  const selectedMarkdown = selectedNode?.markdown ? markdownPreview(selectedNode.markdown) : selectedNode?.objective || "";

  useEffect(() => {
    const svgElement = svgRef.current;
    const wrapperElement = wrapperRef.current;
    if (!svgElement || !wrapperElement) return;

    const width = Math.max(wrapperElement.clientWidth, 520);
    const height = Math.max(wrapperElement.clientHeight, 420);
    const nodes: GraphNode[] = visibleGraph.nodes.map((node) => ({ ...node }));
    const links: GraphLink[] = visibleGraph.links.map((edge) => ({ ...edge }));
    const connected = new Set<string>();
    links.forEach((link) => {
      connected.add(endpointId(link.source));
      connected.add(endpointId(link.target));
    });

    const svg = d3.select(svgElement);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const root = svg.append("g");
    svg.call(
      d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.35, 2.8])
        .on("zoom", (event) => root.attr("transform", event.transform))
    );

    const simulation = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink<GraphNode, GraphLink>(links)
          .id((node) => node.id)
          .distance((link) => 92 + 38 * (1 - Number(link.weight || 0.7)))
      )
      .force("charge", d3.forceManyBody().strength(-430))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide<GraphNode>().radius((node) => (node.type === "skill" ? 31 : 24)));

    const link = root
      .append("g")
      .attr("class", "skill-links")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("class", (edge) => `skill-link ${edge.type}`)
      .attr("stroke-width", (edge) => 1.2 + Number(edge.weight || 0.6) * 1.8);

    const node = root
      .append("g")
      .attr("class", "skill-nodes")
      .selectAll<SVGGElement, GraphNode>("g")
      .data(nodes)
      .join("g")
      .attr("class", (item) => `skill-node ${item.id === selectedId ? "selected" : ""}`)
      .on("click", (_, item) => setSelectedId(item.id))
      .on("mouseenter", (_, item) => setHoveredId(item.id))
      .on("mouseleave", () => setHoveredId(""))
      .call(
        d3
          .drag<SVGGElement, GraphNode>()
          .on("start", (event, item) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            item.fx = item.x;
            item.fy = item.y;
          })
          .on("drag", (event, item) => {
            item.fx = event.x;
            item.fy = event.y;
          })
          .on("end", (event, item) => {
            if (!event.active) simulation.alphaTarget(0);
            item.fx = item.x;
            item.fy = item.y;
          })
      );

    node
      .append("circle")
      .attr("r", (item) => (item.type === "skill" ? 18 : 13))
      .attr("fill", (item) => NODE_COLORS[item.type] || "#c6d2a3")
      .attr("stroke", (item) => (connected.has(item.id) ? "#101316" : "#ff9f8a"))
      .attr("stroke-width", (item) => (item.id === selectedId ? 4 : connected.has(item.id) ? 2 : 3));

    node
      .append("text")
      .attr("x", 24)
      .attr("y", 4)
      .text((item) => item.label || item.id);

    simulation.on("tick", () => {
      link
        .attr("x1", (edge) => (edge.source as GraphNode).x || 0)
        .attr("y1", (edge) => (edge.source as GraphNode).y || 0)
        .attr("x2", (edge) => (edge.target as GraphNode).x || 0)
        .attr("y2", (edge) => (edge.target as GraphNode).y || 0);

      node.attr("transform", (item) => `translate(${item.x || 0},${item.y || 0})`);
    });

    return () => simulation.stop();
  }, [selectedId, visibleGraph]);

  return (
    <section className="skill-system">
      <header className="skill-toolbar">
        <div>
          <h2>Skill Ecosystem</h2>
          <span>
            {graph ? `${graph.nodes.length} nodes · ${graph.edges.length} relationships` : "Loading graph"} · {liveStatus}
          </span>
        </div>
        <div className="skill-controls">
          <select aria-label="Filter by skill type" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            {allTypes.map((type) => (
              <option key={type} value={type}>
                {type === "all" ? "All types" : type.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <select aria-label="Filter by relationship" value={edgeFilter} onChange={(event) => setEdgeFilter(event.target.value)}>
            <option value="all">All edges</option>
            {EDGE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <button onClick={() => readSkillGraph().then(setGraph)}>Refresh</button>
        </div>
      </header>

      <div className="skill-layout">
        <div className="skill-canvas" ref={wrapperRef}>
          <svg ref={svgRef} role="img" aria-label="Live skill ecosystem graph" />
          {hoveredId ? (
            <div className="skill-hover">
              <strong>{hoveredId}</strong>
              {hoverDependencies.length ? hoverDependencies.map((item) => <span key={item}>{item}</span>) : <span>No relationships</span>}
            </div>
          ) : null}
        </div>

        <aside className="skill-side">
          <section className="skill-detail">
            <h3>{selectedNode?.label || "Select a skill"}</h3>
            <span>{selectedNode ? `${selectedNode.type}${selectedNode.status ? ` · ${selectedNode.status}` : ""}` : "Node details"}</span>
            <p>{selectedMarkdown || "Click a graph node to inspect Markdown, dependencies, DNA triggers, and fitness."}</p>
            {selectedNode?.dependencies?.length ? <small>Depends on: {selectedNode.dependencies.join(", ")}</small> : null}
            {selectedNode?.triggers?.length ? <small>Triggers: {selectedNode.triggers.join(", ")}</small> : null}
            {selectedNode?.fitness ? (
              <div className="fitness-grid">
                {Object.entries(selectedNode.fitness).map(([key, value]) => (
                  <span key={key}>
                    {key.replaceAll("_", " ")} <strong>{Number(value).toFixed(2)}</strong>
                  </span>
                ))}
              </div>
            ) : null}
          </section>

          <MetricList title="Most Used" empty="No usage data.">
            {graph?.insights.most_used_skills?.slice(0, 5).map((skill) => (
              <button className="metric-row" key={skill.id} onClick={() => setSelectedId(skill.id)}>
                <span>{skill.id}</span>
                <strong>{skill.usage_frequency.toFixed(2)}</strong>
              </button>
            ))}
          </MetricList>

          <MetricList title="New Skills" empty="No new skill events.">
            {newlyCreated.slice(0, 5).map((id) => (
              <button className="metric-row" key={id} onClick={() => setSelectedId(id)}>
                <span>{id}</span>
                <strong>new</strong>
              </button>
            ))}
          </MetricList>

          <MetricList title="Orphans" empty="No orphan skills.">
            {graph?.insights.isolated_skills?.slice(0, 5).map((id) => (
              <button className="metric-row" key={id} onClick={() => setSelectedId(id)}>
                <span>{id}</span>
                <strong>0</strong>
              </button>
            ))}
          </MetricList>

          <MetricList title="Strong Clusters" empty="No clusters yet.">
            {graph?.clusters.slice(0, 5).map((cluster: SkillCluster) => (
              <button className="metric-row" key={cluster.id} onClick={() => setSelectedId(cluster.members[0] || "")}>
                <span>{cluster.label}</span>
                <strong>{cluster.size}</strong>
              </button>
            ))}
          </MetricList>
        </aside>
      </div>
    </section>
  );
}
