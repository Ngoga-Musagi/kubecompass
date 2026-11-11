"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  CalendarDays,
  CalendarPlus,
  Download,
  Footprints,
  Info,
  Shuffle,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { AgendaButton, FormatBadge, SessionMeta, shortRoom } from "@/components/sessions/session-parts";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { useConference } from "@/hooks/use-conference";
import { useAgenda, useAgendaMutations, useKeys, useProfile, useRecommendations } from "@/hooks/use-data";
import { api, downloadIcs } from "@/lib/api";
import { formatDay, formatTime, sessionHref, tzAbbrev } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AgendaEntry, AgendaView } from "@/types/api";

function minutesLabel(m: number) {
  const h = Math.floor(m / 60);
  return h ? `${h}h${m % 60 ? ` ${m % 60}m` : ""}` : `${m}m`;
}

function Alternatives({ sessionId, onClose }: { sessionId: string | null; onClose: () => void }) {
  const q = useQuery({ queryKey: ["alternatives", sessionId], queryFn: () => api.sessionAlternatives(sessionId!), enabled: !!sessionId });
  return (
    <Sheet open={!!sessionId} onOpenChange={(o) => !o && onClose()} title="Alternatives" description="Similar sessions, with those that fit the rest of your agenda first.">
      {q.isLoading && <Skeleton className="h-64" />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && q.data.length === 0 && <EmptyState title="No close alternatives found" />}
      <ul className="space-y-3">
        {q.data?.map((a) => (
          <li key={a.session.id} className="rounded-xl border border-line p-3">
            <div className="mb-1 flex items-center gap-2">
              {a.fits_agenda ? <Badge tone="explore">Fits your agenda</Badge> : <Badge tone="warn">Also conflicts</Badge>}
            </div>
            <Link href={sessionHref(a.session.id)} className="text-[14px] font-medium leading-snug text-ink hover:underline">
              {a.session.title}
            </Link>
            <SessionMeta session={a.session} className="mt-1" />
            <p className="mt-1.5 text-[12px] text-ink-3">{a.reason}</p>
            <div className="mt-2">
              <AgendaButton sessionId={a.session.id} />
            </div>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

function Entry({ entry, view, onAlternatives }: { entry: AgendaEntry; view: AgendaView; onAlternatives: (id: string) => void }) {
  const { timeZone } = useConference();
  const { remove } = useAgendaMutations();
  const s = entry.session;
  const conflictTitles = view.conflicts.filter((c) => c.session_ids.includes(s.id)).map((c) => c.titles[c.session_ids[0] === s.id ? 1 : 0]);
  const transition = view.transitions.find((t) => t.to_session_id === s.id);
  return (
    <li className="relative grid grid-cols-[76px_1fr] gap-4 sm:grid-cols-[96px_1fr]">
      <div className="pr-3 pt-4 text-right">
        <p className="font-mono text-[12.5px] text-ink">{formatTime(s.starts_at, timeZone)}</p>
        <p className="font-mono text-[11px] text-ink-4">{formatTime(s.ends_at, timeZone)}</p>
      </div>
      <div className="relative pb-3">
        <span className={cn("absolute -left-[21px] top-5 size-2.5 rounded-full border-2 border-bg", entry.conflicts_with.length ? "bg-warn" : "bg-ink")} />
        {transition && (
          <p className="mb-2 flex items-center gap-1.5 text-[12px] text-warn">
            <Footprints className="size-3.5" /> {transition.reason}
          </p>
        )}
        <article className={cn("card p-4", entry.conflicts_with.length && "border-warn/40 bg-warn-soft/30")}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <FormatBadge format={s.format} level={s.audience_level} />
              <Link href={sessionHref(s.id)} className="mt-1.5 block text-[15px] font-semibold leading-snug text-ink hover:underline">
                {s.title}
              </Link>
              <p className="mt-1 text-[12.5px] text-ink-3">
                {s.room ? shortRoom(s.room) : "Room TBA"}
                {s.speakers.length > 0 && ` · ${s.speakers.map((p) => p.full_name).join(", ")}`}
              </p>
            </div>
            <div className="flex gap-1.5">
              {entry.conflicts_with.length > 0 && (
                <Button size="sm" variant="secondary" onClick={() => onAlternatives(s.id)}>
                  <Shuffle /> Alternatives
                </Button>
              )}
              <Button size="icon-sm" variant="ghost" onClick={() => remove.mutate(s.id)} aria-label={`Remove ${s.title}`} disabled={remove.isPending}>
                <Trash2 />
              </Button>
            </div>
          </div>
          {conflictTitles.length > 0 && (
            <p className="mt-3 flex items-start gap-1.5 text-[12.5px] text-warn">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              <span>Overlaps with “{conflictTitles.join("”, “")}”. Pick one, or find an alternative time.</span>
            </p>
          )}
          {entry.change && (
            <p className="mt-3 flex items-start gap-1.5 text-[12.5px] text-high">
              <BellRing className="mt-0.5 size-3.5 shrink-0" />
              Changed since you saved it: {entry.change.fields.join(", ").replace(/_local/g, "")}.
            </p>
          )}
        </article>
      </div>
    </li>
  );
}

export default function AgendaPage() {
  const { conference, timeZone } = useConference();
  const agenda = useAgenda();
  const profile = useProfile();
  const hasProfile = !!profile.data && (profile.data.primary_interests.length > 0 || !!profile.data.intent_text);
  const recs = useRecommendations(undefined, hasProfile);
  const [alt, setAlt] = React.useState<string | null>(null);
  const [day, setDay] = React.useState<string | null>(null);
  const toast = useToast();
  const qc = useQueryClient();
  const keys = useKeys();

  const view = agenda.data;
  const days = view?.days ?? [];
  const activeDay = day && days.some((d) => d.day === day) ? day : (days[0]?.day ?? null);
  const current = days.find((d) => d.day === activeDay);
  const fits = recs.data
    ? [...recs.data.must_attend, ...recs.data.highly_relevant].filter((r) => !r.agenda.in_agenda && r.agenda.conflicts_with.length === 0).slice(0, 5)
    : [];

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow mb-2">My agenda</div>
          <h1 className="font-display text-[38px] leading-tight">Your week at {conference?.short_name ?? "the conference"}</h1>
          <p className="mt-1 text-[14px] text-ink-3">
            {view ? `${view.total} saved · ${view.conflicts.length} conflict${view.conflicts.length === 1 ? "" : "s"} · ` : ""}
            Times in {timeZone.replace("_", " ")} ({tzAbbrev(null, timeZone)})
          </p>
        </div>
        <Button
          variant="primary"
          disabled={!view?.total}
          onClick={() =>
            downloadIcs(`${conference?.id ?? "agenda"}-concompass.ics`)
              .then(() => toast({ tone: "success", title: "Calendar file downloaded", description: "Import it into Google Calendar, Outlook or Apple Calendar." }))
              .catch(() => toast({ tone: "error", title: "Export failed" }))
          }
        >
          <Download /> Export .ics
        </Button>
      </div>

      <p className="mb-6 flex items-start gap-2 rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[12.5px] text-ink-3">
        <Info className="mt-0.5 size-3.5 shrink-0" />
        {view?.seating_notice ?? "Saving a session does not reserve a seat. Seating is subject to event policies and availability."}
      </p>

      {agenda.isLoading && <Skeleton className="h-96" />}
      {agenda.isError && <ErrorState error={agenda.error} onRetry={() => agenda.refetch()} />}

      {view && view.notices.length > 0 && (
        <div className="mb-6 rounded-xl border border-high/30 bg-high-soft/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="flex items-center gap-2 text-[13.5px] font-medium text-ink">
              <BellRing className="size-4 text-high" /> {view.notices.length} saved session{view.notices.length > 1 ? "s" : ""} changed in the official schedule
            </p>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => api.acknowledgeChanges().then((v) => qc.setQueryData(keys.agenda, v))}
            >
              Got it
            </Button>
          </div>
          <ul className="mt-2 space-y-1 text-[12.5px] text-ink-2">
            {view.notices.map((n) => (
              <li key={n.session_id}>
                <span className="font-medium">{n.title}</span>:{" "}
                {n.kind === "removed"
                  ? "removed from the schedule"
                  : n.fields.map((f) => `${f.replace("_local", "")} ${n.before[f] ?? "?"} → ${n.after[f] ?? "?"}`).join("; ")}
              </li>
            ))}
          </ul>
        </div>
      )}

      {view && view.total === 0 && (
        <EmptyState
          icon={CalendarDays}
          title="Your agenda is empty"
          description="Add sessions from your recommendations or search. conCompass will flag conflicts and tight room changes."
          action={
            <Button variant="primary" asChild>
              <Link href="/">
                <CalendarPlus /> Find sessions
              </Link>
            </Button>
          }
        />
      )}

      {view && view.total > 0 && (
        <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0">
            <div role="tablist" aria-label="Conference days" className="mb-5 flex gap-1 overflow-x-auto pb-1">
              {days.map((d) => {
                const conflicts = d.entries.filter((e) => e.conflicts_with.length).length;
                return (
                  <button
                    key={d.day}
                    role="tab"
                    aria-selected={d.day === activeDay}
                    onClick={() => setDay(d.day)}
                    className={cn("flex shrink-0 flex-col items-start rounded-xl border px-3.5 py-2 text-left transition-colors", d.day === activeDay ? "border-ink bg-ink text-bg" : "border-line bg-surface text-ink-2 hover:border-line-strong")}
                  >
                    <span className="text-[13px] font-medium">{formatDay(d.day)}</span>
                    <span className={cn("font-mono text-[10.5px]", d.day === activeDay ? "text-bg/70" : "text-ink-3")}>
                      {d.entries.length} session{d.entries.length === 1 ? "" : "s"}
                      {conflicts ? ` · ${conflicts} ⚠` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
            {current && (
              <div className="relative">
                <span aria-hidden className="absolute bottom-0 left-[76px] top-0 w-px bg-line sm:left-[96px]" />
                <ol>
                  {current.entries.map((e, i) => {
                    const gap = current.gaps.find((g) => i > 0 && g.end === e.session.starts_at);
                    return (
                      <React.Fragment key={e.session.id}>
                        {gap && (
                          <li className="grid grid-cols-[76px_1fr] gap-4 sm:grid-cols-[96px_1fr]">
                            <span />
                            <p className="py-2 text-[12px] text-ink-4">
                              {minutesLabel(gap.minutes)} free · {formatTime(gap.start, timeZone)} – {formatTime(gap.end, timeZone)}
                            </p>
                          </li>
                        )}
                        <Entry entry={e} view={view} onAlternatives={setAlt} />
                      </React.Fragment>
                    );
                  })}
                </ol>
              </div>
            )}
            {view.unscheduled.length > 0 && <p className="mt-4 text-[12.5px] text-ink-3">{view.unscheduled.length} saved session(s) have no published time yet.</p>}
          </div>
          <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
            <section className="card p-4">
              <h2 className="eyebrow mb-1">Fits your schedule</h2>
              <p className="mb-3 text-[12.5px] text-ink-3">Recommended sessions that don&apos;t overlap anything you&apos;ve saved.</p>
              {!hasProfile && (
                <p className="text-[12.5px] text-ink-3">
                  <Link href="/" className="text-needle-ink hover:underline">
                    Describe your interests
                  </Link>{" "}
                  to get suggestions here.
                </p>
              )}
              {recs.isLoading && <Skeleton className="h-40" />}
              {hasProfile && recs.data && fits.length === 0 && <p className="text-[12.5px] text-ink-3">No conflict-free recommendations left. Nice coverage.</p>}
              <ul className="space-y-3">
                {fits.map((r) => (
                  <li key={r.session.id} className="border-t border-line pt-3 first:border-0 first:pt-0">
                    <Link href={sessionHref(r.session.id)} className="line-clamp-2 text-[13px] font-medium leading-snug text-ink hover:underline">
                      {r.session.title}
                    </Link>
                    <SessionMeta session={r.session} className="mt-1" />
                    <div className="mt-2">
                      <AgendaButton sessionId={r.session.id} />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </aside>
        </div>
      )}
      <Alternatives sessionId={alt} onClose={() => setAlt(null)} />
    </div>
  );
}
