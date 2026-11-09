"use client";

import { CalendarCheck2, CalendarPlus, Clock, MapPin, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Avatar, Badge, Tooltip } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { useAgendaIds, useAgendaMutations } from "@/hooks/use-data";
import { entityHref, formatDay, formatLabel, formatTimeRange, speakerHref, tzAbbrev } from "@/lib/format";
import { cn, entityColor, ENTITY_LABEL, ORIGIN_COPY } from "@/lib/utils";
import type { EntityRef, Origin, SessionSummary, SpeakerBrief } from "@/types/api";

export function OriginBadge({ origin, className }: { origin: Origin | string; className?: string }) {
  const copy = ORIGIN_COPY[origin] ?? { label: origin, hint: "" };
  const tone = origin === "explicit" ? "outline" : origin === "inferred" ? "high" : "neutral";
  return (
    <Tooltip content={copy.hint}>
      <span tabIndex={0}>
        <Badge tone={tone} className={cn("h-[18px] px-1 font-mono text-[9.5px] uppercase tracking-wider", className)}>
          {copy.label}
        </Badge>
      </span>
    </Tooltip>
  );
}

export function EntityChip({
  entity,
  size = "sm",
  showEvidence = true,
}: {
  entity: Pick<EntityRef, "id" | "name" | "type"> & Partial<Pick<EntityRef, "origin" | "evidence">>;
  size?: "sm" | "md";
  showEvidence?: boolean;
}) {
  const chip = (
    <Link
      href={entityHref(entity.id)}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-surface text-ink-2 transition-colors hover:border-line-strong hover:text-ink",
        size === "sm" ? "h-6 px-2 text-[11.5px]" : "h-7 px-2.5 text-[12.5px]",
      )}
    >
      <span className="size-1.5 shrink-0 rounded-full" style={{ background: entityColor(entity.type) }} />
      <span className="truncate">{entity.name}</span>
    </Link>
  );
  if (!showEvidence || !entity.origin) return chip;
  return (
    <Tooltip
      content={
        <span className="block">
          <span className="font-medium">
            {ENTITY_LABEL[entity.type] ?? entity.type} · {ORIGIN_COPY[entity.origin]?.label ?? entity.origin}
          </span>
          {entity.evidence && <span className="mt-1 block opacity-80">“{entity.evidence}”</span>}
        </span>
      }
    >
      {chip}
    </Tooltip>
  );
}

export function SessionMeta({ session, className, showDay = true }: { session: SessionSummary; className?: string; showDay?: boolean }) {
  const { timeZone } = useConference();
  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-ink-3", className)}>
      <span className="inline-flex items-center gap-1">
        <Clock className="size-3.5" />
        {showDay && session.day ? `${formatDay(session.day)} · ` : ""}
        {formatTimeRange(session.starts_at, session.ends_at, timeZone)}
        {session.starts_at && <span className="text-ink-4">{tzAbbrev(session.starts_at, timeZone)}</span>}
      </span>
      {session.room && (
        <span className="inline-flex min-w-0 items-center gap-1">
          <MapPin className="size-3.5 shrink-0" />
          <span className="truncate">{shortRoom(session.room)}</span>
        </span>
      )}
    </div>
  );
}

/** "Salt Palace | Level 2 | 250 A-C" -> "250 A-C · Salt Palace L2" */
export function shortRoom(room: string): string {
  const parts = room.split("|").map((p) => p.trim()).filter(Boolean);
  if (parts.length < 2) return room;
  const venue = parts[0];
  const level = parts.find((p) => /^level/i.test(p))?.replace(/level\s*/i, "L");
  const name = parts[parts.length - 1];
  return `${name} · ${venue}${level ? ` ${level}` : ""}`;
}

export function FormatBadge({ format, level }: { format: string; level?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge tone="neutral">{formatLabel(format)}</Badge>
      {level && <Badge tone="outline">{level}</Badge>}
    </span>
  );
}

export function SpeakerLine({ speakers, max = 3 }: { speakers: SpeakerBrief[]; max?: number }) {
  if (!speakers.length) return null;
  const shown = speakers.slice(0, max);
  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className="flex -space-x-1.5">
        {shown.map((s) => (
          <Avatar key={s.id} name={s.full_name} src={s.photo_url} size={22} />
        ))}
      </div>
      <p className="min-w-0 truncate text-[12.5px] text-ink-2">
        {shown.map((s, i) => (
          <span key={s.id}>
            {i > 0 && ", "}
            <Link href={speakerHref(s.id)} className="hover:text-ink hover:underline">
              {s.full_name}
            </Link>
            {s.company && <span className="text-ink-3"> ({s.company})</span>}
          </span>
        ))}
        {speakers.length > max && <span className="text-ink-3"> +{speakers.length - max}</span>}
      </p>
    </div>
  );
}

export function AgendaButton({
  sessionId,
  conflicts = [],
  size = "sm",
  className,
}: {
  sessionId: string;
  conflicts?: string[];
  size?: "sm" | "md";
  className?: string;
}) {
  const ids = useAgendaIds();
  const { add, remove } = useAgendaMutations();
  const saved = ids.has(sessionId);
  const busy = (add.isPending && add.variables === sessionId) || (remove.isPending && remove.variables === sessionId);
  if (saved) {
    return (
      <Button
        size={size}
        variant="subtle"
        disabled={busy}
        onClick={(e) => {
          e.preventDefault();
          remove.mutate(sessionId);
        }}
        className={cn("text-ok", className)}
        aria-label="Remove from agenda"
      >
        <CalendarCheck2 /> In agenda
      </Button>
    );
  }
  const btn = (
    <Button
      size={size}
      variant={conflicts.length ? "secondary" : "primary"}
      disabled={busy}
      onClick={(e) => {
        e.preventDefault();
        add.mutate(sessionId);
      }}
      className={className}
    >
      {conflicts.length ? <TriangleAlert className="text-warn" /> : <CalendarPlus />}
      Add to agenda
    </Button>
  );
  return conflicts.length ? (
    <Tooltip content={`Overlaps ${conflicts.length} session${conflicts.length > 1 ? "s" : ""} already in your agenda`}>{btn}</Tooltip>
  ) : (
    btn
  );
}

/** Relevance "bearing": a small compass arc. The value is the computed recommendation score. */
export function Bearing({ value, tier, size = 40 }: { value: number; tier: "must_attend" | "highly_relevant" | "explore"; size?: number }) {
  const r = size / 2 - 3;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  const color = tier === "must_attend" ? "var(--tier-must)" : tier === "highly_relevant" ? "var(--tier-high)" : "var(--tier-explore)";
  const angle = -135 + 270 * v;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth="3" strokeDasharray={`${c * 0.75} ${c}`} transform={`rotate(135 ${size / 2} ${size / 2})`} strokeLinecap="round" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="3" strokeDasharray={`${c * 0.75 * v} ${c}`} transform={`rotate(135 ${size / 2} ${size / 2})`} strokeLinecap="round" />
      <line x1={size / 2} y1={size / 2} x2={size / 2} y2={size / 2 - r + 6} stroke="var(--ink)" strokeWidth="1.6" strokeLinecap="round" transform={`rotate(${angle} ${size / 2} ${size / 2})`} />
      <circle cx={size / 2} cy={size / 2} r="2" fill="var(--ink)" />
    </svg>
  );
}

export const TIER_COPY = {
  must_attend: { label: "Must attend", tone: "must" as const, dot: "bg-must" },
  highly_relevant: { label: "Highly relevant", tone: "high" as const, dot: "bg-high" },
  explore: { label: "Explore", tone: "explore" as const, dot: "bg-explore" },
};
