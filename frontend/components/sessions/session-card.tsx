"use client";

import Link from "next/link";

import {
  AgendaButton,
  EntityChip,
  FormatBadge,
  SessionMeta,
  SpeakerLine,
} from "@/components/sessions/session-parts";
import { sessionHref } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { SessionSummary } from "@/types/api";

/** Generic session card for search results, lists and knowledge pages. */
export function SessionCard({
  session,
  highlights,
  footer,
  evidence,
  className,
  compact = false,
}: {
  session: SessionSummary;
  highlights?: string[];
  footer?: React.ReactNode;
  evidence?: React.ReactNode;
  className?: string;
  compact?: boolean;
}) {
  const chips = [...session.technologies.slice(0, 3), ...session.topics.slice(0, 3)];
  return (
    <article className={cn("card group relative flex min-w-0 flex-col gap-3 p-4 transition-[border-color,box-shadow] hover:border-line-strong hover:shadow-[var(--shadow-md)]", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <FormatBadge format={session.format} level={session.audience_level} />
            {session.track && <span className="truncate text-[12px] text-ink-3">{session.track}</span>}
          </div>
          <h3 className="text-[15px] font-semibold leading-snug tracking-tight text-ink">
            <Link href={sessionHref(session.id)} className="after:absolute after:inset-0 hover:underline focus-visible:outline-none">
              <span className="relative">{session.title}</span>
            </Link>
          </h3>
        </div>
        <div className="relative z-10 shrink-0">
          <AgendaButton sessionId={session.id} />
        </div>
      </div>
      <SessionMeta session={session} />
      {!compact && (
        <div className="relative z-10">
          <SpeakerLine speakers={session.speakers} />
        </div>
      )}
      {highlights && highlights.length > 0 && (
        <p
          className="line-clamp-2 text-[13px] leading-relaxed text-ink-2"
          // Highlights come from Elasticsearch with only <mark> tags around source text.
          dangerouslySetInnerHTML={{ __html: sanitizeHighlight(highlights[0] ?? "") }}
        />
      )}
      {evidence}
      {!compact && chips.length > 0 && (
        <div className="relative z-10 flex flex-wrap gap-1.5">
          {chips.map((e) => (
            <EntityChip key={e.id} entity={e} />
          ))}
        </div>
      )}
      {footer && <div className="relative z-10">{footer}</div>}
    </article>
  );
}

/** Escape everything, then re-allow only <mark>/</mark> emitted by the highlighter. */
export function sanitizeHighlight(html: string): string {
  const escaped = html.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return escaped.replace(/&lt;mark&gt;/g, "<mark>").replace(/&lt;\/mark&gt;/g, "</mark>");
}
