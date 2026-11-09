"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, Lightbulb, Route, TriangleAlert, Users } from "lucide-react";
import Link from "next/link";

import { EntityChip, shortRoom } from "@/components/sessions/session-parts";
import { Avatar, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { useAgenda, useKeys } from "@/hooks/use-data";
import { api } from "@/lib/api";
import { entityHref, formatDay, formatTime, sessionHref, speakerHref } from "@/lib/format";
import { cn, entityColor } from "@/lib/utils";
import type { RecommendationResponse } from "@/types/api";

export function Pathways() {
  const keys = useKeys();
  const { conference } = useConference();
  const q = useQuery({ queryKey: keys.pathways, queryFn: api.pathways, enabled: !!conference });
  return (
    <section aria-labelledby="pathways-title">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="eyebrow mb-1.5 flex items-center gap-1.5">
            <Route className="size-3" /> Discovery pathways
          </div>
          <h2 id="pathways-title" className="text-[17px] font-semibold tracking-tight">
            Where this conference goes deep
          </h2>
          <p className="mt-1 text-[13px] text-ink-3">Topic areas derived from session content, with real session counts.</p>
        </div>
        <Link href="/graph" className="inline-flex items-center gap-1 text-[12.5px] text-ink-2 hover:text-ink">
          Explore the graph <ArrowRight className="size-3.5" />
        </Link>
      </div>
      {q.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-[168px]" />
          ))}
        </div>
      )}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {q.data.map((p, i) => (
            <article
              key={p.entity.id}
              className={cn("card relative flex min-w-0 animate-rise flex-col p-4 transition-[border-color,box-shadow] hover:border-line-strong hover:shadow-[var(--shadow-md)]", p.profile_match && "ring-1 ring-needle/30")}
              style={{ animationDelay: `${i * 35}ms` }}
            >
              <div className="flex items-start justify-between gap-2">
                <Link href={entityHref(p.entity.id)} className="text-[14.5px] font-semibold leading-snug text-ink after:absolute after:inset-0 hover:underline">
                  {p.entity.name}
                </Link>
                <span className="shrink-0 font-mono text-[11px] text-ink-3">{p.session_count} sessions</span>
              </div>
              {p.profile_match && <span className="mt-1 text-[11.5px] font-medium text-needle-ink">Matches your profile</span>}
              {p.children.length > 0 && (
                <div className="relative z-10 mt-3 flex flex-wrap gap-1">
                  {p.children.slice(0, 4).map((c) => (
                    <EntityChip key={c.id} entity={c} showEvidence={false} />
                  ))}
                </div>
              )}
              <ul className="relative z-10 mt-3 space-y-1 border-t border-line pt-3">
                {p.sample_sessions.slice(0, 2).map((s) => (
                  <li key={s.id} className="truncate text-[12.5px]">
                    <Link href={sessionHref(s.id)} className="text-ink-2 hover:text-ink hover:underline">
                      {s.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function Insights({ data }: { data: RecommendationResponse }) {
  const { insights } = data;
  const empty = !insights.top_topics.length && !insights.speakers.length;
  return (
    <section className="card p-5" aria-labelledby="insights-title">
      <div className="eyebrow mb-1 flex items-center gap-1.5">
        <Lightbulb className="size-3" /> Discovery insights
      </div>
      <h2 id="insights-title" className="mb-4 text-[15px] font-semibold">
        What stands out for you
      </h2>
      {empty ? (
        <p className="text-[13px] text-ink-3">Insights appear once you have recommendations.</p>
      ) : (
        <div className="space-y-5">
          {insights.top_topics.length > 0 && (
            <div>
              <p className="eyebrow mb-2">Your strongest topics</p>
              <ul className="space-y-1.5">
                {insights.top_topics.slice(0, 5).map((t) => {
                  const max = insights.top_topics[0]?.count ?? 1;
                  return (
                    <li key={t.id}>
                      <Link href={entityHref(t.id)} className="group grid grid-cols-[1fr_auto] items-center gap-x-3 text-[12.5px]">
                        <span className="truncate text-ink-2 group-hover:text-ink">{t.name}</span>
                        <span className="font-mono text-[11px] text-ink-3">{t.count}</span>
                        <span className="col-span-2 mt-1 h-1 overflow-hidden rounded-full bg-surface-3">
                          <span className="block h-full rounded-full" style={{ width: `${(t.count / max) * 100}%`, background: entityColor(t.type) }} />
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          {insights.related_technologies.length > 0 && (
            <div>
              <p className="eyebrow mb-2">Technologies you didn&apos;t mention</p>
              <div className="flex flex-wrap gap-1.5">
                {insights.related_technologies.slice(0, 8).map((t) => (
                  <EntityChip key={t.id} entity={{ id: t.id, name: t.name, type: t.type as never }} showEvidence={false} />
                ))}
              </div>
            </div>
          )}
          {insights.speakers.length > 0 && (
            <div>
              <p className="eyebrow mb-2 flex items-center gap-1.5">
                <Users className="size-3" /> People to seek out
              </p>
              <ul className="space-y-2.5">
                {insights.speakers.slice(0, 5).map(({ speaker, reason }) => (
                  <li key={speaker.id}>
                    <Link href={speakerHref(speaker.id)} className="group flex items-center gap-2.5">
                      <Avatar name={speaker.full_name} src={speaker.photo_url} size={28} />
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-medium text-ink group-hover:underline">{speaker.full_name}</span>
                        <span className="block truncate text-[11.5px] text-ink-3">{reason}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function AgendaPreview() {
  const { data, isLoading, isError, error, refetch } = useAgenda();
  const { timeZone } = useConference();
  const entries = (data?.days ?? []).flatMap((d) => d.entries);
  const now = Date.now();
  const upcoming = entries.filter((e) => e.session.ends_at && new Date(e.session.ends_at).getTime() > now);
  const shown = (upcoming.length ? upcoming : entries).slice(0, 4);
  return (
    <section className="card p-5" aria-labelledby="agenda-preview-title">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="eyebrow mb-1 flex items-center gap-1.5">
            <CalendarDays className="size-3" /> Your agenda
          </div>
          <h2 id="agenda-preview-title" className="text-[15px] font-semibold">
            {upcoming.length ? "Coming up" : "Saved sessions"}
          </h2>
        </div>
        <Link href="/agenda" className="text-[12.5px] text-ink-2 hover:text-ink">
          Open
        </Link>
      </div>
      {isLoading && <Skeleton className="h-32" />}
      {isError && <ErrorState error={error} onRetry={() => refetch()} />}
      {data && data.conflicts.length > 0 && (
        <Link href="/agenda" className="mb-3 flex items-center gap-2 rounded-lg bg-warn-soft px-3 py-2 text-[12.5px] text-warn">
          <TriangleAlert className="size-3.5" />
          {data.conflicts.length} time conflict{data.conflicts.length > 1 ? "s" : ""} to resolve
        </Link>
      )}
      {data && entries.length === 0 && (
        <EmptyState icon={CalendarDays} title="No sessions saved yet" description="Add recommendations to build your week." className="py-8" />
      )}
      {shown.length > 0 && (
        <ol className="relative space-y-3 border-l border-line pl-4">
          {shown.map((e) => (
            <li key={e.session.id} className="relative">
              <span className={cn("absolute -left-[21px] top-1.5 size-2.5 rounded-full border-2 border-surface", e.conflicts_with.length ? "bg-warn" : "bg-ink")} />
              <p className="font-mono text-[11px] text-ink-3">
                {e.session.day && formatDay(e.session.day)} · {formatTime(e.session.starts_at, timeZone)}
              </p>
              <Link href={sessionHref(e.session.id)} className="line-clamp-2 text-[13px] font-medium leading-snug text-ink hover:underline">
                {e.session.title}
              </Link>
              {e.session.room && <p className="truncate text-[11.5px] text-ink-3">{shortRoom(e.session.room)}</p>}
            </li>
          ))}
        </ol>
      )}
      {data && data.total > shown.length && <p className="mt-3 text-[12px] text-ink-3">+{data.total - shown.length} more in your agenda</p>}
    </section>
  );
}
