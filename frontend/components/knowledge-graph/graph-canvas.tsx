"use client";

import type { Core, ElementDefinition } from "cytoscape";
import * as React from "react";

import type { GraphEdge, GraphNode } from "@/types/api";

export interface GraphCanvasHandle {
  fit: () => void;
  focus: (id: string) => void;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

function truncate(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/** Cytoscape canvas. Elements are diffed in place so expansion animates instead of re-rendering. */
export const GraphCanvas = React.forwardRef<
  GraphCanvasHandle,
  {
    nodes: GraphNode[];
    edges: GraphEdge[];
    center: string | null;
    selected: string | null;
    onSelect: (id: string | null) => void;
    onExpand: (id: string) => void;
    dark: boolean;
  }
>(function GraphCanvas({ nodes, edges, center, selected, onSelect, onExpand, dark }, ref) {
  const container = React.useRef<HTMLDivElement>(null);
  const cy = React.useRef<Core | null>(null);
  const handlers = React.useRef({ onSelect, onExpand });
  handlers.current = { onSelect, onExpand };

  React.useImperativeHandle(ref, () => ({
    fit: () => cy.current?.animate({ fit: { eles: cy.current.elements(), padding: 40 } }, { duration: 300 }),
    focus: (id: string) => {
      const n = cy.current?.getElementById(id);
      if (n && n.nonempty()) cy.current?.animate({ center: { eles: n }, zoom: Math.max(cy.current.zoom(), 1) }, { duration: 300 });
    },
  }));

  // Init once.
  React.useEffect(() => {
    let disposed = false;
    (async () => {
      const [{ default: cytoscape }, { default: fcose }] = await Promise.all([import("cytoscape"), import("cytoscape-fcose")]);
      if (disposed || !container.current) return;
      try {
        cytoscape.use(fcose);
      } catch {
        /* already registered */
      }
      const instance = cytoscape({
        container: container.current,
        minZoom: 0.25,
        maxZoom: 1.6,
        boxSelectionEnabled: false,
      });
      instance.on("tap", "node", (e) => handlers.current.onSelect(e.target.id()));
      instance.on("dbltap", "node", (e) => handlers.current.onExpand(e.target.id()));
      instance.on("tap", (e) => {
        if (e.target === instance) handlers.current.onSelect(null);
      });
      cy.current = instance;
      container.current.dispatchEvent(new Event("cy-ready"));
    })();
    return () => {
      disposed = true;
      cy.current?.destroy();
      cy.current = null;
    };
  }, []);

  // Style (re-applied on theme change).
  const applyStyle = React.useCallback(() => {
    const c = cy.current;
    if (!c) return;
    const ink = cssVar("--ink");
    const ink3 = cssVar("--ink-3");
    const surface = cssVar("--surface");
    const line = cssVar("--border-strong");
    c.style([
      {
        selector: "node",
        style: {
          "background-color": "data(color)",
          width: "data(size)",
          height: "data(size)",
          label: "data(label)",
          color: ink,
          "font-size": 10,
          "min-zoomed-font-size": 7,
          "font-family": "Inter, system-ui, sans-serif",
          "text-valign": "bottom",
          "text-margin-y": 5,
          "text-wrap": "wrap",
          "text-max-width": "120px",
          "text-background-color": surface,
          "text-background-opacity": 0.85,
          "text-background-padding": "2px",
          "text-background-shape": "roundrectangle",
          "border-width": 2,
          "border-color": surface,
          "transition-property": "background-color, width, height, border-color, opacity",
          "transition-duration": 200,
        },
      },
      { selector: "node[type = 'session']", style: { shape: "round-rectangle", "font-size": 9, "text-max-width": "110px" } },
      { selector: "node[type = 'speaker']", style: { shape: "ellipse" } },
      { selector: "node[type = 'organization']", style: { shape: "round-diamond" } },
      { selector: "node[type = 'track']", style: { shape: "round-tag" } },
      { selector: "node.center", style: { "border-width": 3, "border-color": ink, "font-weight": 600, "font-size": 13 } },
      { selector: "node:selected, node.selected", style: { "border-width": 3, "border-color": cssVar("--needle") } },
      { selector: "node.faded", style: { opacity: 0.25 } },
      {
        selector: "edge",
        style: {
          width: "mapData(confidence, 0, 1, 0.6, 2.2)",
          "line-color": line,
          "curve-style": "bezier",
          opacity: 0.8,
          "target-arrow-shape": "none",
        },
      },
      { selector: "edge[origin = 'explicit']", style: { "line-color": ink3 } },
      { selector: "edge[origin = 'inferred']", style: { "line-style": "dashed", "line-color": cssVar("--tier-high") } },
      { selector: "edge[origin = 'curated']", style: { "line-style": "dotted" } },
      { selector: "edge.highlight", style: { opacity: 1, width: 2.5, "line-color": cssVar("--needle") } },
      { selector: "edge.faded", style: { opacity: 0.12 } },
    ]);
  }, []);

  React.useEffect(() => {
    const t = setTimeout(applyStyle, 0);
    return () => clearTimeout(t);
  }, [dark, applyStyle]);

  // Sync elements.
  React.useEffect(() => {
    const sync = () => {
      const c = cy.current;
      if (!c) return false;
      const colors: Record<string, string> = {};
      ["topic", "technology", "project", "speaker", "organization", "session", "track"].forEach((t) => (colors[t] = cssVar(`--ent-${t}`)));
      const wanted = new Set([...nodes.map((n) => n.id), ...edges.map((e) => `e:${e.id}`)]);
      c.elements().forEach((el) => {
        if (!wanted.has(el.id())) el.remove();
      });
      const newNodes: ElementDefinition[] = [];
      nodes.forEach((n) => {
        const size = n.type === "session" ? 16 : Math.min(54, 18 + Math.sqrt(n.session_count ?? 1) * 4.2);
        const data = {
          id: n.id,
          label: truncate(n.name, n.type === "session" ? 34 : 28),
          type: n.type,
          color: colors[n.type] ?? "#888",
          size: n.id === center ? size + 10 : size,
        };
        const existing = c.getElementById(n.id);
        if (existing.nonempty()) existing.data(data);
        else newNodes.push({ group: "nodes", data });
      });
      if (newNodes.length) c.add(newNodes);
      const newEdges: ElementDefinition[] = edges
        .filter((e) => c.getElementById(`e:${e.id}`).empty())
        .filter((e) => c.getElementById(e.source).nonempty() && c.getElementById(e.target).nonempty())
        .map((e) => ({ group: "edges", data: { id: `e:${e.id}`, source: e.source, target: e.target, origin: e.origin, confidence: e.confidence } }));
      if (newEdges.length) c.add(newEdges);
      c.nodes().removeClass("center");
      if (center) c.getElementById(center).addClass("center");
      applyStyle();
      if (newNodes.length || newEdges.length) {
        c.layout({
          name: "fcose",
          animate: true,
          animationDuration: 450,
          randomize: c.nodes().length === newNodes.length,
          nodeRepulsion: () => 16000,
          idealEdgeLength: () => 110,
          nodeSeparation: 80,
          padding: 40,
        } as never).run();
      }
      return true;
    };
    if (!sync()) {
      const el = container.current;
      const onReady = () => sync();
      el?.addEventListener("cy-ready", onReady, { once: true });
      return () => el?.removeEventListener("cy-ready", onReady);
    }
  }, [nodes, edges, center, applyStyle]);

  // Selection highlight.
  React.useEffect(() => {
    const c = cy.current;
    if (!c) return;
    c.elements().removeClass("faded highlight selected");
    if (!selected) return;
    const n = c.getElementById(selected);
    if (n.empty()) return;
    n.addClass("selected");
    const hood = n.closedNeighborhood();
    c.elements().not(hood).addClass("faded");
    n.connectedEdges().addClass("highlight");
  }, [selected, nodes]);

  // Cytoscape forces position:relative on its container, so it fills a positioned shell.
  return (
    <div className="absolute inset-0">
      <div ref={container} className="h-full w-full" role="img" aria-label="Interactive knowledge graph. Use the panel to search and select nodes." />
    </div>
  );
});
