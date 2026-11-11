"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CalendarCheck, CalendarPlus, CalendarSync, CalendarX, Info, Loader2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { SessionMeta } from "@/components/sessions/session-parts";
import { Button } from "@/components/ui/button";
import { Avatar, Badge } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { sessionHref, speakerHref } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AgentCard, ProposedAction } from "@/types/api";

/** Runs a proposed action only when the attendee clicks it (that click is the confirmation). */
function ActionButton({ action, prominent }: { action: ProposedAction; prominent?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [done, setDone] = React.useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api.agentAction(action.tool, action.args),
    onSuccess: (r) => {
      setDone(r.reply);
      void qc.invalidateQueries({ queryKey: ["agenda"] });
      void qc.invalidateQueries({ queryKey: ["recommendations"] });
      void qc.invalidateQueries({ queryKey: ["agent"] });
    },
    onError: (e) => toast({ tone: "error", title: e instanceof ApiError ? e.message : "That didn't work. Try again." }),
  });
  if (done) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-ok" role="status">
        <CalendarCheck className="size-4" /> {done}
      </span>
    );
  }
  const removing = action.tool === "remove_session_from_agenda";
  const syncing = action.tool === "sync_agenda_to_calendar";
  const text = prominent ? (removing ? "Yes, remove" : syncing ? "Yes, sync" : "Yes, add it") : action.label;
  return (
    <Button
      size="sm"
      variant={prominent ? (removing ? "danger" : "accent") : "secondary"}
      disabled={run.isPending}
      onClick={() => run.mutate()}
      // Accessible name starts with the visible text (WCAG "label in name"), then adds context.
      aria-label={`${text}: ${action.description}`}
    >
      {run.isPending ? <Loader2 className="animate-spin" /> : removing ? <CalendarX /> : syncing ? <CalendarSync /> : <CalendarPlus />}
      {text}
    </Button>
  );
}

function SessionCard({ card }: { card: AgentCard }) {
  const s = card.session!;
  return (
    <article className="card p-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {card.badge && <Badge tone={card.badge === "Conflict" ? "warn" : "needle"}>{card.badge}</Badge>}
        {card.in_agenda && card.badge !== "Saved" && <Badge tone="outline">In your agenda</Badge>}
        {card.fits_agenda === false && !card.in_agenda && <Badge tone="warn">Overlaps your agenda</Badge>}
      </div>
      <Link href={sessionHref(s.id)} className="mt-1.5 block text-[14px] font-medium leading-snug hover:underline">
        {s.title}
      </Link>
      <SessionMeta session={s} className="mt-1" />
      {card.detail && <p className="mt-2 text-[12.5px] leading-relaxed text-ink-2">{card.detail}</p>}
      {card.action && card.type === "session" && (
        <div className="mt-3">
          <ActionButton action={card.action} />
        </div>
      )}
    </article>
  );
}

function ConfirmCard({ card }: { card: AgentCard }) {
  const [dismissed, setDismissed] = React.useState(false);
  if (dismissed) return <p className="text-[12.5px] text-ink-3">Okay, no changes made.</p>;
  return (
    <article className="rounded-[14px] border border-needle/40 bg-needle-soft/30 p-3.5" aria-label="Confirm agenda change">
      <p className="eyebrow mb-1.5 text-needle-ink">{card.title ?? "Please confirm"}</p>
      {card.session && (
        <>
          <Link href={sessionHref(card.session.id)} className="text-[14px] font-medium leading-snug hover:underline">
            {card.session.title}
          </Link>
          <SessionMeta session={card.session} className="mt-1" />
        </>
      )}
      {card.detail && !card.session && <p className="text-[13px] leading-relaxed text-ink-2">{card.detail}</p>}
      {card.fits_agenda === false && (
        <p className="mt-2 flex items-center gap-1.5 text-[12.5px] text-warn">
          <AlertTriangle className="size-3.5" /> Overlaps a session you already saved.
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {card.action && <ActionButton action={card.action} prominent />}
        <Button size="sm" variant="ghost" onClick={() => setDismissed(true)}>
          Cancel
        </Button>
      </div>
    </article>
  );
}

export function AgentCards({ cards }: { cards: AgentCard[] }) {
  if (cards.length === 0) return null;
  const sessions = cards.filter((c) => c.type === "session" && c.session);
  const others = cards.filter((c) => !(c.type === "session" && c.session));
  return (
    <div className="space-y-2.5">
      {others.map((c, i) => {
        if (c.type === "action") return <ConfirmCard key={`a${i}`} card={c} />;
        if (c.type === "speaker" && c.speaker)
          return (
            <Link key={c.speaker.id} href={speakerHref(c.speaker.id)} className="card flex items-center gap-2.5 p-2.5 hover:border-line-strong">
              <Avatar name={c.speaker.full_name} src={c.speaker.photo_url} size={32} />
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-medium">{c.speaker.full_name}</span>
                <span className="block truncate text-[11.5px] text-ink-3">
                  {[c.speaker.job_title, c.speaker.company].filter(Boolean).join(" · ")}
                </span>
              </span>
            </Link>
          );
        const warn = c.type === "conflict";
        return (
          <div
            key={`n${i}`}
            role={warn ? "alert" : undefined}
            className={cn(
              "flex gap-2.5 rounded-xl border p-3 text-[13px]",
              warn ? "border-warn/30 bg-warn-soft/60" : "border-line bg-surface-2",
            )}
          >
            {warn ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" /> : <Info className="mt-0.5 size-4 shrink-0 text-ink-3" />}
            <span>
              {c.title && <span className="font-medium text-ink">{c.title}. </span>}
              <span className="text-ink-2">{c.detail}</span>
            </span>
          </div>
        );
      })}
      {sessions.length > 0 && (
        <div className="grid gap-2.5 md:grid-cols-2">
          {sessions.map((c) => (
            <SessionCard key={c.session!.id} card={c} />
          ))}
        </div>
      )}
    </div>
  );
}
