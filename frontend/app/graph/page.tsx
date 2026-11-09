"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, ChevronRight, Expand, Info, Maximize2, RotateCcw, Search } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import { GraphCanvas, type GraphCanvasHandle } from "@/components/knowledge-graph/graph-canvas";
import { OriginBadge } from "@/components/sessions/session-parts";
import { Button } from "@/components/ui/button";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { useProfile } from "@/hooks/use-data";
import { api } from "@/lib/api";
import { entityHref, sessionHref, speakerHref } from "@/lib/format";
import { cn, entityColor, ENTITY_LABEL } from "@/lib/utils";
import type { GraphEdge, GraphNode, GraphResponse } from "@/types/api";

const TYPES = ["topic", "technology", "project", "session", "speaker", "organization"] as const;
const REL_COPY: Record<string, string> = {
  PRESENTS: "presents",
  COVERS: "covers",
  USES: "uses",
  DISCUSSES: "discusses",
  WORKS_ON: "works on",
  ASSOCIATED_WITH: "is associated with",
  BELONGS_TO_TRACK: "is in track",
  RELATED_TO: "is related to",
  PART_OF: "is part of",
};

function hrefFor(n: GraphNode) {
  if (n.type === "session") return sessionHref(n.id);
  if (n.type === "speaker") return speakerHref(n.id);
  return entityHref(n.id);
}

function useIsDark() {
  const [dark, setDark] = React.useState(false);
  React.useEffect(() => {
    const el = document.documentElement;
    const update = () => setDark(el.classList.contains("dark"));
    update();
    const obs = new MutationObserver(update);
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

function merge(a: GraphResponse | null, b: GraphResponse): GraphResponse {
  if (!a) return b;
  const nodes = new Map(a.nodes.map((n) => [n.id, n]));
  b.nodes.forEach((n) => nodes.set(n.id, n));
  const edges = new Map(a.edges.map((e) => [e.id, e]));
  b.edges.forEach((e) => edges.set(e.id, e));
  return { center: b.center, nodes: [...nodes.values()], edges: [...edges.values()], truncated: b.truncated };
}

function GraphExplorer() {
  const params = useSearchParams();
  const focus = params.get("focus");
  const { conference } = useConference();
  const profile = useProfile();
  const dark = useIsDark();
  const canvas = React.useRef<GraphCanvasHandle>(null);

  const [graph, setGraph] = React.useState<GraphResponse | null>(null);
  const [trail, setTrail] = React.useState<GraphNode[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [types, setTypes] = React.useState<Set<string>>(new Set(TYPES));
  const [inferred, setInferred] = React.useState(true);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const [q, setQ] = React.useState("");

  const personalized = !!profile.data?.primary_interests.length;

  const loadOverview = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const g = await api.graphOverview({ per_type: 9, personalized });
      setGraph(g);
      setTrail([]);
      setSelected(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [personalized]);

  const expand = React.useCallback(
    async (id: string, replace = false) => {
      setLoading(true);
      setError(null);
      try {
        const g = await api.graphNeighborhood(id, { limit: 8, include_inferred: inferred, types: [...types, "track"] });
        setGraph((cur) => (replace ? g : merge(cur, g)));
        const center = g.nodes.find((n) => n.id === id);
        if (center) setTrail((t) => (replace ? [center] : [...t.filter((x) => x.id !== id), center]));
        setSelected(id);
        setTimeout(() => canvas.current?.focus(id), 500);
      } catch (e) {
        setError(e);
      } finally {
        setLoading(false);
      }
    },
    [inferred, types],
  );

  React.useEffect(() => {
    if (!conference || profile.isLoading) return;
    if (focus) void expand(focus, true);
    else void loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial load per conference/focus
  }, [conference?.id, focus, profile.isLoading]);

  const search = useQuery({
    queryKey: ["graph-search", q],
    queryFn: () => api.graphSearch(q),
    enabled: q.trim().length >= 2,
  });

  const visibleNodes = React.useMemo(
    () => (graph?.nodes ?? []).filter((n) => types.has(n.type) || n.type === "track" || n.id === graph?.center),
    [graph, types],
  );
  const visibleIds = React.useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);
  const visibleEdges = React.useMemo(
    () => (graph?.edges ?? []).filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target) && (inferred || e.origin !== "inferred")),
    [graph, visibleIds, inferred],
  );

  const selNode = graph?.nodes.find((n) => n.id === selected) ?? null;
  const selEdges: { edge: GraphEdge; other: GraphNode }[] = React.useMemo(() => {
    if (!selected || !graph) return [];
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    return visibleEdges
      .filter((e) => e.source === selected || e.target === selected)
      .map((e) => ({ edge: e, other: byId.get(e.source === selected ? e.target : e.source)! }))
      .filter((x) => x.other)
      .sort((a, b) => (a.edge.origin === "explicit" ? -1 : 0) - (b.edge.origin === "explicit" ? -1 : 0));
  }, [selected, graph, visibleEdges]);

  return (
    <div className="-mx-4 -mb-24 -mt-6 grid h-[calc(100dvh-56px)] grid-rows-[auto_1fr] sm:-mx-6 lg:-mx-8 lg:grid-cols-[340px_minmax(0,1fr)] lg:grid-rows-1">
      <aside className="scrollbar-thin overflow-y-auto border-b border-line bg-bg p-4 lg:border-b-0 lg:border-r">
        <div className="eyebrow mb-1">Knowledge graph</div>
        <h1 className="mb-1 text-[18px] font-semibold tracking-tight">Explore connections</h1>
        <p className="mb-4 text-[12.5px] leading-relaxed text-ink-3">
          {personalized ? "Starting from your interests. " : "Starting from the most-covered concepts. "}Click a node for evidence; double-click to expand its neighborhood.
        </p>

        <div className="relative mb-4">
          <div className="flex h-9 items-center gap-2 rounded-[10px] border border-line bg-surface px-2.5 focus-within:border-ink/40">
            <Search className="size-4 text-ink-3" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a topic, technology or speaker" className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-ink-4" aria-label="Find in graph" />
          </div>
          {q.trim().length >= 2 && search.data && (
            <ul className="absolute inset-x-0 top-10 z-20 max-h-72 overflow-auto rounded-xl border border-line bg-surface p-1 shadow-[var(--shadow-lg)]">
              {[...search.data.entities, ...search.data.speakers].length === 0 && <li className="px-3 py-2 text-[12.5px] text-ink-3">Nothing found.</li>}
              {[...search.data.entities, ...search.data.speakers].map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => {
                      setQ("");
                      void expand(r.id, true);
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] hover:bg-surface-2"
                  >
                    <span className="size-2 rounded-full" style={{ background: entityColor(r.type) }} />
                    <span className="flex-1 truncate">{r.name}</span>
                    <span className="text-[11px] text-ink-3">{ENTITY_LABEL[r.type]}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <fieldset className="mb-4">
          <legend className="eyebrow mb-2">Show</legend>
          <div className="flex flex-wrap gap-1.5">
            {TYPES.map((t) => {
              const on = types.has(t);
              return (
                <button
                  key={t}
                  aria-pressed={on}
                  onClick={() => setTypes((cur) => {
                    const next = new Set(cur);
                    if (next.has(t)) next.delete(t);
                    else next.add(t);
                    return next;
                  })}
                  className={cn("inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[12px] transition-colors", on ? "border-line-strong bg-surface text-ink" : "border-dashed border-line text-ink-4")}
                >
                  <span className="size-2 rounded-full" style={{ background: on ? entityColor(t) : "var(--ink-4)" }} />
                  {ENTITY_LABEL[t]}
                </button>
              );
            })}
          </div>
          <label className="mt-3 flex items-center gap-2 text-[12.5px] text-ink-2">
            <input type="checkbox" checked={inferred} onChange={(e) => setInferred(e.target.checked)} className="accent-[var(--needle)]" />
            Include inferred connections
          </label>
        </fieldset>

        {trail.length > 0 && (
          <nav aria-label="Exploration path" className="mb-4">
            <p className="eyebrow mb-1.5">Your path</p>
            <ol className="flex flex-wrap items-center gap-1 text-[12px]">
              {trail.map((n, i) => (
                <li key={n.id} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="size-3 text-ink-4" />}
                  <button onClick={() => { setSelected(n.id); canvas.current?.focus(n.id); }} className="max-w-[140px] truncate rounded px-1 text-ink-2 hover:bg-surface-2 hover:text-ink">
                    {n.name}
                  </button>
                </li>
              ))}
            </ol>
          </nav>
        )}

        {error ? <ErrorState error={error} onRetry={() => void loadOverview()} className="mb-4" /> : null}

        {selNode ? (
          <section className="card animate-fade p-4" aria-live="polite">
            <div className="mb-1 flex items-center gap-2">
              <span className="size-2.5 rounded-full" style={{ background: entityColor(selNode.type) }} />
              <span className="eyebrow">{ENTITY_LABEL[selNode.type]}</span>
            </div>
            <h2 className="text-[15px] font-semibold leading-snug">{selNode.name}</h2>
            {selNode.session_count != null && selNode.type !== "session" && <p className="mt-0.5 text-[12px] text-ink-3">{selNode.session_count} sessions</p>}
            {selNode.meta?.company && <p className="mt-0.5 text-[12px] text-ink-3">{selNode.meta.company}</p>}
            <div className="mt-3 flex gap-2">
              <Button size="sm" variant="primary" onClick={() => void expand(selNode.id)} disabled={loading}>
                <Expand /> Expand
              </Button>
              <Button size="sm" variant="secondary" asChild>
                <Link href={hrefFor(selNode)}>
                  Open <ArrowUpRight />
                </Link>
              </Button>
            </div>
            {selEdges.length > 0 && (
              <div className="mt-4 border-t border-line pt-3">
                <p className="eyebrow mb-2">Connections & evidence</p>
                <ul className="space-y-2.5">
                  {selEdges.slice(0, 14).map(({ edge, other }) => {
                    const outgoing = edge.source === selNode.id;
                    return (
                      <li key={edge.id} className="text-[12.5px] leading-snug">
                        <div className="flex items-start justify-between gap-2">
                          <button onClick={() => { setSelected(other.id); canvas.current?.focus(other.id); }} className="text-left text-ink-2 hover:text-ink">
                            <span className="text-ink-3">{outgoing ? REL_COPY[edge.type] ?? edge.type : `← ${REL_COPY[edge.type] ?? edge.type}`} </span>
                            <span className="font-medium text-ink">{other.name}</span>
                          </button>
                          <OriginBadge origin={edge.origin} />
                        </div>
                        {edge.evidence && <p className="mt-0.5 line-clamp-2 text-[11.5px] text-ink-4">{edge.evidence}</p>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </section>
        ) : (
          <div className="flex items-start gap-2 rounded-xl border border-dashed border-line-strong p-3 text-[12px] text-ink-3">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            Select a node to see how it connects, and the evidence behind each connection.
          </div>
        )}

        <div className="mt-4 space-y-1.5 text-[11.5px] text-ink-3">
          <p className="eyebrow">Edges</p>
          <p className="flex items-center gap-2"><span className="h-px w-6 bg-ink-3" /> Official schedule data</p>
          <p className="flex items-center gap-2"><span className="h-px w-6 bg-line-strong" /> Extracted from text</p>
          <p className="flex items-center gap-2"><span className="w-6 border-t border-dotted border-ink-3" /> Curated hierarchy</p>
          <p className="flex items-center gap-2"><span className="w-6 border-t border-dashed border-high" /> Inferred (similarity / co-occurrence)</p>
        </div>
      </aside>

      <section className="relative min-h-[420px] overflow-hidden bg-surface-2/40" style={{ backgroundImage: "radial-gradient(var(--border) 1px, transparent 1px)", backgroundSize: "22px 22px" }}>
        {!graph && loading && <Skeleton className="absolute inset-8" />}
        <GraphCanvas ref={canvas} nodes={visibleNodes} edges={visibleEdges} center={graph?.center ?? null} selected={selected} onSelect={setSelected} onExpand={(id) => void expand(id)} dark={dark} />
        <div className="absolute right-3 top-3 flex gap-1.5">
          {loading && <span className="flex h-8 items-center rounded-lg bg-surface px-2.5 text-[12px] text-ink-3 shadow-[var(--shadow-sm)]">Loading…</span>}
          <Button size="sm" variant="secondary" onClick={() => canvas.current?.fit()} aria-label="Fit graph to screen">
            <Maximize2 /> Fit
          </Button>
          <Button size="sm" variant="secondary" onClick={() => void loadOverview()}>
            <RotateCcw /> Reset
          </Button>
        </div>
        {graph && Object.keys(graph.truncated).length > 0 && (
          <p className="absolute bottom-3 left-3 rounded-lg bg-surface/90 px-2.5 py-1.5 text-[11.5px] text-ink-3 shadow-[var(--shadow-sm)]">
            Showing the strongest connections; {Object.entries(graph.truncated).map(([t, n]) => `${n} more ${t}s`).join(", ")} hidden to keep the view readable.
          </p>
        )}
      </section>
    </div>
  );
}

export default function GraphPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-[70vh]" />}>
      <GraphExplorer />
    </React.Suspense>
  );
}
