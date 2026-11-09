"use client";

import { useQuery } from "@tanstack/react-query";
import { Search as SearchIcon, SlidersHorizontal, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { SessionCard } from "@/components/sessions/session-card";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, ErrorState, Segmented, Skeleton, Tooltip } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { api } from "@/lib/api";
import { formatDay, formatLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FacetValue, SearchMode, SessionFilters } from "@/types/api";

const MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: "hybrid", label: "Hybrid", hint: "BM25 + vector search fused with Reciprocal Rank Fusion" },
  { value: "keyword", label: "Keyword", hint: "BM25 full-text search only" },
  { value: "vector", label: "Semantic", hint: "Dense-vector (kNN) search only" },
];

const FACETS: { key: string; filter: keyof SessionFilters; label: string; fmt?: (v: string) => string }[] = [
  { key: "day", filter: "days", label: "Day", fmt: (v) => formatDay(v, "long") },
  { key: "format", filter: "formats", label: "Format", fmt: formatLabel },
  { key: "audience_level", filter: "audience_levels", label: "Level" },
  { key: "track", filter: "tracks", label: "Track" },
];

function FacetGroup({ label, values, selected, onToggle, fmt, chronological }: { label: string; values: FacetValue[]; selected: string[]; onToggle: (v: string) => void; fmt?: (v: string) => string; chronological?: boolean }) {
  if (!values.length && !selected.length) return null;
  const merged = [...selected.filter((s) => !values.some((v) => v.value === s)).map((s) => ({ value: s, count: 0 })), ...values];
  if (chronological) merged.sort((a, b) => a.value.localeCompare(b.value));
  return (
    <fieldset>
      <legend className="eyebrow mb-2">{label}</legend>
      <div className="space-y-0.5">
        {merged.map((v) => {
          const on = selected.includes(v.value);
          return (
            <label key={v.value} className={cn("flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] transition-colors", on ? "bg-surface text-ink ring-1 ring-line" : "text-ink-2 hover:bg-surface-2")}>
              <input type="checkbox" checked={on} onChange={() => onToggle(v.value)} className="size-3.5 accent-[var(--needle)]" />
              <span className="flex-1 truncate">{fmt ? fmt(v.value) : v.value}</span>
              <span className="font-mono text-[11px] text-ink-4">{v.count || ""}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function SearchPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { conference } = useConference();
  const query = params.get("q") ?? "";
  const mode = (params.get("mode") as SearchMode) || "hybrid";
  const filters: SessionFilters = {
    days: params.getAll("day"),
    formats: params.getAll("format"),
    audience_levels: params.getAll("level"),
    tracks: params.getAll("track"),
    entity_ids: params.getAll("entity"),
  };
  const [draft, setDraft] = React.useState(query);
  const [showFilters, setShowFilters] = React.useState(false);
  React.useEffect(() => setDraft(query), [query]);

  const update = (mut: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(params.toString());
    mut(p);
    router.replace(`/search?${p.toString()}`, { scroll: false });
  };
  const paramName: Record<string, string> = { days: "day", formats: "format", audience_levels: "level", tracks: "track", entity_ids: "entity" };
  const toggle = (filter: keyof SessionFilters, value: string) =>
    update((p) => {
      const name = paramName[filter]!;
      const cur = p.getAll(name);
      p.delete(name);
      (cur.includes(value) ? cur.filter((x) => x !== value) : [...cur, value]).forEach((x) => p.append(name, x));
    });

  const q = useQuery({
    queryKey: ["search", conference?.id, query, mode, filters],
    queryFn: () => api.search({ query, mode, filters, limit: 40 }),
    enabled: !!conference,
    placeholderData: (prev) => prev,
  });
  const activeFilters = Object.entries(filters).flatMap(([k, vs]) => (vs as string[]).map((v) => ({ k: k as keyof SessionFilters, v })));

  const facetPanel = q.data && (
    <div className="space-y-6">
      {FACETS.map((f) => (
        <FacetGroup key={f.key} label={f.label} values={q.data.facets[f.key] ?? []} selected={(filters[f.filter] as string[]) ?? []} onToggle={(v) => toggle(f.filter, v)} fmt={f.fmt} chronological={f.key === "day"} />
      ))}
    </div>
  );

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          update((p) => p.set("q", draft.trim()));
        }}
        className="mb-6 flex flex-wrap items-center gap-3"
      >
        <div className="flex h-11 min-w-[260px] flex-1 items-center gap-2 rounded-xl border border-line-strong bg-surface px-3 focus-within:shadow-[0_0_0_4px_var(--ring)]">
          <SearchIcon className="size-4 text-ink-3" />
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder='Search the schedule: try "GPU sharing" or a natural question' className="flex-1 bg-transparent text-[14.5px] outline-none placeholder:text-ink-4" aria-label="Search query" />
        </div>
        <Segmented label="Retrieval mode" value={mode} onChange={(m) => update((p) => p.set("mode", m))} options={MODES} />
        <Button type="button" variant="secondary" className="lg:hidden" onClick={() => setShowFilters((s) => !s)}>
          <SlidersHorizontal /> Filters
        </Button>
      </form>

      <div className="grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className={cn("lg:block", showFilters ? "block" : "hidden")}>{facetPanel ?? <Skeleton className="h-80" />}</aside>
        <section className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {q.data && (
              <p className="text-[13px] text-ink-3">
                <span className="font-medium text-ink">{q.data.total}</span> {q.data.total === 1 ? "session" : "sessions"}
                {query && (
                  <>
                    {" "}for <span className="text-ink">“{query}”</span>
                  </>
                )}{" "}
                · {q.data.took_ms} ms · {MODES.find((m) => m.value === q.data.mode)?.label ?? q.data.mode}
              </p>
            )}
            {q.data?.degraded.includes("vector_unavailable") && <Badge tone="warn">Semantic search unavailable: keyword results only</Badge>}
            {activeFilters.map(({ k, v }) => (
              <button key={`${k}:${v}`} onClick={() => toggle(k, v)} className="inline-flex h-6 items-center gap-1 rounded-full bg-ink px-2 text-[11.5px] text-bg">
                {k === "days" ? formatDay(v) : k === "formats" ? formatLabel(v) : k === "entity_ids" ? v.split(":")[1] : v}
                <X className="size-3" />
              </button>
            ))}
          </div>
          {q.isLoading && (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-36" />
              ))}
            </div>
          )}
          {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
          {q.data && q.data.hits.length === 0 && (
            <EmptyState icon={SearchIcon} title="No sessions match" description="Try fewer filters, a broader phrase, or switch to Semantic mode." />
          )}
          <div className={cn("space-y-3 transition-opacity", q.isFetching && !q.isLoading && "opacity-60")}>
            {q.data?.hits.map((h) => (
              <SessionCard
                key={h.session.id}
                session={h.session}
                highlights={h.highlights}
                footer={
                  query ? (
                    <div className="flex flex-wrap gap-1.5 text-[11px]">
                      {h.bm25_rank && (
                        <Tooltip content="Rank in BM25 keyword retrieval">
                          <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-ink-3">BM25 #{h.bm25_rank}</span>
                        </Tooltip>
                      )}
                      {h.vector_rank && (
                        <Tooltip content={`Rank in vector retrieval · cosine ${h.vector_similarity?.toFixed(2)}`}>
                          <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-ink-3">Vector #{h.vector_rank}</span>
                        </Tooltip>
                      )}
                    </div>
                  ) : undefined
                }
              />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96" />}>
      <SearchPageInner />
    </React.Suspense>
  );
}
