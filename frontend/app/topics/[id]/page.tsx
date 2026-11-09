"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Network, Search } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { EntityChip, OriginBadge } from "@/components/sessions/session-parts";
import { SessionCard } from "@/components/sessions/session-card";
import { Avatar, Badge, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { api } from "@/lib/api";
import { speakerHref } from "@/lib/format";
import { entityColor, ENTITY_LABEL, ORIGIN_COPY } from "@/lib/utils";

/** Knowledge page for a topic, technology, project, organization or track. */
export default function TopicPage() {
  const { id } = useParams<{ id: string }>();
  const eid = decodeURIComponent(id);
  const { conference } = useConference();
  const q = useQuery({ queryKey: ["entity", eid], queryFn: () => api.graphEntity(eid), enabled: !!conference });
  if (q.isLoading || !conference) return <Skeleton className="h-96" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const sessions = d.sessions.filter((s) => s.session.is_content);
  return (
    <div className="animate-fade">
      <Link href="/graph" className="mb-5 inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink">
        <ArrowLeft className="size-3.5" /> Knowledge graph
      </Link>
      <div className="mb-8">
        <div className="mb-2 flex items-center gap-2">
          <span className="size-2.5 rounded-full" style={{ background: entityColor(d.entity.type) }} />
          <span className="eyebrow">{ENTITY_LABEL[d.entity.type] ?? d.entity.type}</span>
          <OriginBadge origin={d.origin} />
        </div>
        <h1 className="font-display text-[44px] leading-tight">{d.entity.name}</h1>
        <p className="mt-1 text-[14px] text-ink-3">
          {sessions.length} session{sessions.length === 1 ? "" : "s"} · {d.speakers.length} speaker{d.speakers.length === 1 ? "" : "s"} at {conference.short_name}.{" "}
          {ORIGIN_COPY[d.origin]?.hint}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link href={`/graph?focus=${encodeURIComponent(d.entity.id)}`} className="inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-ink px-3.5 text-[13px] font-medium text-bg">
            <Network className="size-4" /> Explore connections
          </Link>
          <Link href={`/search?entity=${encodeURIComponent(d.entity.id)}`} className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border border-line bg-surface px-3.5 text-[13px] text-ink">
            <Search className="size-4" /> Filter the schedule
          </Link>
        </div>
      </div>
      <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="min-w-0">
          <h2 className="eyebrow mb-3">Sessions</h2>
          {sessions.length === 0 && <EmptyState title="No sessions linked to this yet" />}
          <div className="space-y-3">
            {sessions.map((r) => (
              <SessionCard
                key={r.session.id}
                session={r.session}
                evidence={
                  r.evidence ? (
                    <div className="relative z-10 flex items-start gap-2 text-[12px] text-ink-3">
                      <OriginBadge origin={r.origin} />
                      <span className="line-clamp-2">{r.origin === "extracted" ? `“${r.evidence}”` : r.evidence}</span>
                    </div>
                  ) : undefined
                }
              />
            ))}
          </div>
        </section>
        <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          {(d.parents.length > 0 || d.children.length > 0) && (
            <div className="card space-y-3 p-4">
              {d.parents.length > 0 && (
                <div>
                  <p className="eyebrow mb-2">Part of</p>
                  <div className="flex flex-wrap gap-1.5">
                    {d.parents.map((p) => (
                      <EntityChip key={p.id} entity={p} showEvidence={false} />
                    ))}
                  </div>
                </div>
              )}
              {d.children.length > 0 && (
                <div>
                  <p className="eyebrow mb-2">Includes</p>
                  <div className="flex flex-wrap gap-1.5">
                    {d.children.map((p) => (
                      <EntityChip key={p.id} entity={p} showEvidence={false} />
                    ))}
                  </div>
                </div>
              )}
              <p className="text-[11.5px] text-ink-4">Hierarchy from the curated cloud-native vocabulary.</p>
            </div>
          )}
          {d.related.length > 0 && (
            <div className="card p-4">
              <p className="eyebrow mb-2">Often discussed together</p>
              <div className="flex flex-wrap gap-1.5">
                {d.related.map((p) => (
                  <EntityChip key={p.id} entity={p} showEvidence={false} />
                ))}
              </div>
              <p className="mt-2 text-[11.5px] text-ink-4">
                <Badge tone="high" className="mr-1 h-[18px] px-1 font-mono text-[9.5px] uppercase">Inferred</Badge>
                from co-occurrence across session abstracts.
              </p>
            </div>
          )}
          {d.speakers.length > 0 && (
            <div className="card p-4">
              <p className="eyebrow mb-3">People</p>
              <ul className="space-y-2.5">
                {d.speakers.slice(0, 12).map((s) => (
                  <li key={s.id}>
                    <Link href={speakerHref(s.id)} className="flex items-center gap-2.5 hover:underline">
                      <Avatar name={s.full_name} src={s.photo_url} size={28} />
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] text-ink">{s.full_name}</span>
                        {s.company && <span className="block truncate text-[11.5px] text-ink-3">{s.company}</span>}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
