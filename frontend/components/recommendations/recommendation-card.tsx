"use client";

import { ArrowUpRight, ChevronDown, GitBranch, Quote, Target } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  AgendaButton,
  Bearing,
  EntityChip,
  FormatBadge,
  SessionMeta,
  SpeakerLine,
  TIER_COPY,
} from "@/components/sessions/session-parts";
import { Badge, Tooltip } from "@/components/ui/primitives";
import { sessionHref } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Recommendation } from "@/types/api";

const COMPONENT_COPY: Record<string, { label: string; hint: string }> = {
  interest_match: { label: "Interest match", hint: "Elasticsearch hybrid retrieval: BM25 strength plus semantic similarity to what you described." },
  topic_technology: { label: "Topics & technologies", hint: "Overlap between your profile and the session's linked topics, weighted by extraction confidence." },
  graph_relevance: { label: "Knowledge graph", hint: "Personalized PageRank from your interests across the conference knowledge graph." },
  learning_goal: { label: "Learning goals", hint: "Semantic similarity between your stated goals and the session abstract." },
  novelty: { label: "Discovery", hint: "Reachable from your interests but brings in topics you didn't mention." },
  format_preference: { label: "Format & level", hint: "Your preferred formats and experience level." },
};

export function ScoreBreakdown({ rec, weights }: { rec: Recommendation; weights: Record<string, number> }) {
  return (
    <div className="space-y-2">
      {Object.entries(COMPONENT_COPY).map(([key, copy]) => {
        const v = rec.components[key] ?? 0;
        const w = weights[key] ?? 0;
        return (
          <Tooltip key={key} content={copy.hint} side="left">
            <div className="grid grid-cols-[120px_1fr_70px] items-center gap-3 text-[12px]">
              <span className="truncate text-ink-2">{copy.label}</span>
              <span className="h-1.5 overflow-hidden rounded-full bg-surface-3">
                <span className="block h-full rounded-full bg-ink/70" style={{ width: `${Math.round(v * 100)}%` }} />
              </span>
              <span className="text-right font-mono text-[11px] text-ink-3">
                {v.toFixed(2)} × {w.toFixed(2)}
              </span>
            </div>
          </Tooltip>
        );
      })}
      <p className="pt-1 text-[11.5px] text-ink-3">
        Score {rec.score.toFixed(3)} = Σ signal × weight. Weights are configurable defaults, not tuned optima.
      </p>
    </div>
  );
}

export function RecommendationCard({
  rec,
  weights,
  index = 0,
}: {
  rec: Recommendation;
  weights: Record<string, number>;
  index?: number;
}) {
  const [open, setOpen] = React.useState(false);
  const s = rec.session;
  const tier = TIER_COPY[rec.tier];
  const ex = rec.explanation;
  return (
    <article
      className="card flex min-w-0 animate-rise flex-col p-5 transition-[border-color,box-shadow] hover:border-line-strong hover:shadow-[var(--shadow-md)]"
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <div className="flex items-start gap-3">
        <Bearing value={rec.score} tier={rec.tier} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={tier.tone}>
              <span className={cn("size-1.5 rounded-full", tier.dot)} />
              {tier.label}
            </Badge>
            <span className="text-[12px] capitalize text-ink-3">{ex.match_type} match</span>
          </div>
          <p className="mt-1 text-[12.5px] leading-snug text-ink-2">{ex.summary}</p>
        </div>
      </div>

      <h3 className="mt-4 text-[16.5px] font-semibold leading-snug tracking-tight text-ink">
        <Link href={sessionHref(s.id)} className="hover:underline">
          {s.title}
        </Link>
      </h3>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        <FormatBadge format={s.format} level={s.audience_level} />
        <SessionMeta session={s} />
      </div>
      {s.track && <p className="mt-1.5 text-[12px] text-ink-3">{s.track}</p>}
      <div className="mt-3">
        <SpeakerLine speakers={s.speakers} />
      </div>

      {ex.reasons.length > 0 && (
        <ul className="mt-4 space-y-1.5">
          {ex.reasons.slice(0, 3).map((r) => (
            <li key={r} className="flex gap-2 text-[13px] leading-snug text-ink-2">
              <Target className="mt-0.5 size-3.5 shrink-0 text-ink-4" />
              <span>{r}</span>
            </li>
          ))}
        </ul>
      )}

      {ex.learn[0] && (
        <figure className="mt-4 rounded-xl border border-line bg-surface-2/60 p-3">
          <figcaption className="eyebrow mb-1 flex items-center gap-1.5">
            <Quote className="size-3" /> What you&apos;ll learn · from the abstract
          </figcaption>
          <blockquote className="line-clamp-3 text-[13px] leading-relaxed text-ink-2">{ex.learn[0]}</blockquote>
        </figure>
      )}

      {ex.matched_entities.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {ex.matched_entities.slice(0, 6).map((m) => (
            <EntityChip key={m.id} entity={{ ...m, type: m.type as never }} />
          ))}
        </div>
      )}

      {rec.related.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="eyebrow mb-1.5 flex items-center gap-1.5">
            <GitBranch className="size-3" /> Related
          </p>
          <ul className="space-y-1">
            {rec.related.map((r) => (
              <li key={r.id} className="truncate text-[12.5px]">
                <Link href={sessionHref(r.id)} className="text-ink-2 hover:text-ink hover:underline">
                  {r.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
        <button
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink"
        >
          <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
          How this was ranked
        </button>
        <div className="flex items-center gap-2">
          <Link href={sessionHref(s.id)} className="inline-flex h-8 items-center gap-1 rounded-[10px] px-2.5 text-[12.5px] text-ink-2 hover:bg-surface-2 hover:text-ink">
            Details <ArrowUpRight className="size-3.5" />
          </Link>
          <AgendaButton sessionId={s.id} conflicts={rec.agenda.conflicts_with} />
        </div>
      </div>
      {open && (
        <div className="mt-3 animate-fade rounded-xl bg-surface-2/60 p-3">
          <ScoreBreakdown rec={rec} weights={weights} />
        </div>
      )}
    </article>
  );
}

/** Dense row used for the longer "Highly relevant" list. */
export function RecommendationRow({ rec }: { rec: Recommendation }) {
  const s = rec.session;
  return (
    <div className="group flex items-start gap-3 px-4 py-3.5 transition-colors hover:bg-surface-2/60">
      <Bearing value={rec.score} tier={rec.tier} size={30} />
      <div className="min-w-0 flex-1">
        <Link href={sessionHref(s.id)} className="block text-[14px] font-medium leading-snug text-ink hover:underline">
          {s.title}
        </Link>
        <p className="mt-0.5 line-clamp-1 text-[12.5px] text-ink-3">{rec.explanation.summary}</p>
        <SessionMeta session={s} className="mt-1.5" />
      </div>
      <AgendaButton sessionId={s.id} conflicts={rec.agenda.conflicts_with} className="shrink-0" />
    </div>
  );
}
