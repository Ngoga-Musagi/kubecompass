"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ExternalLink,
  FileText,
  GitBranch,
  Github,
  Globe,
  MapPin,
  MonitorPlay,
  Network,
  Sparkles,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { ScoreBreakdown } from "@/components/recommendations/recommendation-card";
import {
  AgendaButton,
  EntityChip,
  FormatBadge,
  OriginBadge,
  SessionMeta,
  TIER_COPY,
} from "@/components/sessions/session-parts";
import { Avatar, Badge, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { useProfile, useRecommendations } from "@/hooks/use-data";
import { api } from "@/lib/api";
import { formatLabel, sessionHref, speakerHref } from "@/lib/format";
import { cn, ENTITY_LABEL } from "@/lib/utils";
import type { EntityRef, Resource, SessionDetail } from "@/types/api";

const RESOURCE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  slides: FileText,
  repository: Github,
  demo: MonitorPlay,
  website: Globe,
  location_map: MapPin,
  recording: MonitorPlay,
};

function Abstract({ text }: { text: string }) {
  return (
    <div className="space-y-3 text-[15px] leading-[1.7] text-ink-2">
      {text.split(/\n{2,}/).map((para, i) => (
        <p key={i} className="whitespace-pre-line">
          {para}
        </p>
      ))}
    </div>
  );
}

function EntityGroup({ title, entities }: { title: string; entities: EntityRef[] }) {
  if (!entities.length) return null;
  return (
    <div>
      <p className="eyebrow mb-2">{title}</p>
      <ul className="space-y-2">
        {entities.map((e) => (
          <li key={e.id} className="flex items-start gap-2">
            <EntityChip entity={e} />
            <OriginBadge origin={e.origin} className="mt-0.5" />
            {e.evidence && e.origin !== "explicit" && (
              <span className="hidden min-w-0 flex-1 truncate pt-0.5 text-[11.5px] text-ink-4 lg:block" title={e.evidence}>
                “{e.evidence}”
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function WhyForYou({ session }: { session: SessionDetail }) {
  const profile = useProfile();
  const active = !!profile.data && (profile.data.primary_interests.length > 0 || !!profile.data.intent_text);
  const recs = useRecommendations(undefined, active);
  if (!active) {
    return (
      <div className="card p-4">
        <p className="text-[13px] text-ink-2">
          <Link href="/" className="font-medium text-needle-ink hover:underline">
            Describe what you want to learn
          </Link>{" "}
          to see how this session fits your goals.
        </p>
      </div>
    );
  }
  if (recs.isLoading) return <Skeleton className="h-32" />;
  const all = recs.data ? [...recs.data.must_attend, ...recs.data.highly_relevant, ...recs.data.explore] : [];
  const rec = all.find((r) => r.session.id === session.id);
  if (!rec || !recs.data) {
    return (
      <div className="card p-4">
        <div className="eyebrow mb-1">For you</div>
        <p className="text-[13px] text-ink-2">Not among your current recommendations. It doesn&apos;t strongly match the interests in your profile.</p>
      </div>
    );
  }
  const tier = TIER_COPY[rec.tier];
  return (
    <div className="card p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="eyebrow flex items-center gap-1.5">
          <Sparkles className="size-3" /> Why it&apos;s relevant to you
        </div>
        <Badge tone={tier.tone}>{tier.label}</Badge>
      </div>
      <p className="text-[13px] font-medium text-ink">{rec.explanation.summary}</p>
      <ul className="mt-2 space-y-1">
        {rec.explanation.reasons.map((r) => (
          <li key={r} className="text-[12.5px] leading-snug text-ink-2">
            · {r}
          </li>
        ))}
      </ul>
      {rec.explanation.supported_goals.length > 0 && (
        <p className="mt-2 text-[12.5px] text-ink-3">Supports your goal: “{rec.explanation.supported_goals[0]}”</p>
      )}
      <div className="mt-3 rounded-lg bg-surface-2/60 p-3">
        <ScoreBreakdown rec={rec} weights={recs.data.weights} />
      </div>
    </div>
  );
}

export default function SessionPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const { conference } = useConference();
  const q = useQuery({ queryKey: ["session", id], queryFn: () => api.session(id), enabled: !!conference });

  if (q.isLoading || !conference) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-12 w-3/4" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data!;
  const topics = s.entities.filter((e) => e.type === "topic");
  const tech = s.entities.filter((e) => e.type === "technology");
  const projects = s.entities.filter((e) => e.type === "project");
  const resources = s.resources.filter((r) => r.kind !== "location_map");
  const mapLink = s.resources.find((r) => r.kind === "location_map");

  return (
    <article className="animate-fade">
      <Link href="/" className="mb-5 inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink">
        <ArrowLeft className="size-3.5" /> Back to discovery
      </Link>
      <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <FormatBadge format={s.format} level={s.audience_level} />
            {s.track && <Badge tone="outline">{s.track}</Badge>}
            {s.subtopics.map((t) => (
              <Badge key={t} tone="outline">
                {t}
              </Badge>
            ))}
            {s.flags.includes("end_user") && <Badge tone="needle">End-user talk</Badge>}
            {s.flags.includes("sponsored") && <Badge tone="neutral">Sponsored</Badge>}
          </div>
          <h1 className="font-display text-[34px] leading-[1.08] tracking-[-0.005em] text-ink sm:text-[42px]">{s.title}</h1>
          <SessionMeta session={s} className="mt-4 text-[13px]" />
          <div className="mt-5 flex flex-wrap gap-2">
            <AgendaButton sessionId={s.id} size="md" />
            {mapLink && (
              <a href={mapLink.url} target="_blank" rel="noopener noreferrer" className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border border-line bg-surface px-3.5 text-[13px] text-ink hover:bg-surface-2">
                <MapPin className="size-4" /> Venue map
              </a>
            )}
          </div>

          <section className="mt-8">
            <h2 className="eyebrow mb-3">About this session</h2>
            {s.description ? <Abstract text={s.description} /> : <p className="text-[14px] text-ink-3">No abstract was published for this session.</p>}
          </section>

          {s.speakers.length > 0 && (
            <section className="mt-10">
              <h2 className="eyebrow mb-3 flex items-center gap-1.5">
                <Users className="size-3" /> Speakers
              </h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {s.speakers.map((sp) => (
                  <Link key={sp.id} href={speakerHref(sp.id)} className="card flex items-center gap-3 p-3 hover:border-line-strong">
                    <Avatar name={sp.full_name} src={sp.photo_url} size={44} />
                    <span className="min-w-0">
                      <span className="block truncate text-[14px] font-medium text-ink">{sp.full_name}</span>
                      <span className="block truncate text-[12.5px] text-ink-3">{[sp.job_title, sp.company].filter(Boolean).join(" · ")}</span>
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          )}

          <section className="mt-10">
            <h2 className="eyebrow mb-3 flex items-center gap-1.5">
              <GitBranch className="size-3" /> Related sessions
            </h2>
            {s.related.length === 0 ? (
              <EmptyState title="No closely related sessions found" className="py-8" />
            ) : (
              <ul className="card divide-y divide-line overflow-hidden">
                {s.related.map((r) => (
                  <li key={r.session.id} className="flex items-start gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <Link href={sessionHref(r.session.id)} className="text-[14px] font-medium leading-snug text-ink hover:underline">
                        {r.session.title}
                      </Link>
                      <SessionMeta session={r.session} className="mt-1" />
                      {r.evidence && <p className="mt-1 text-[12px] text-ink-3">{r.evidence}</p>}
                    </div>
                    <OriginBadge origin={r.origin} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          <WhyForYou session={s} />
          <div className="card space-y-5 p-4">
            <div className="flex items-center justify-between">
              <h2 className="eyebrow flex items-center gap-1.5">
                <Network className="size-3" /> In the knowledge graph
              </h2>
              <Link href={`/graph?focus=${encodeURIComponent(s.id)}`} className="text-[12px] text-ink-2 hover:text-ink">
                Explore
              </Link>
            </div>
            <EntityGroup title={ENTITY_LABEL.topic + "s"} entities={topics} />
            <EntityGroup title="Technologies" entities={tech} />
            <EntityGroup title="Projects" entities={projects} />
            {!s.entities.length && <p className="text-[13px] text-ink-3">No topics could be linked from the published text.</p>}
          </div>
          {resources.length > 0 && (
            <div className="card p-4">
              <h2 className="eyebrow mb-3">Resources</h2>
              <ul className="space-y-1">
                {resources.map((r: Resource) => {
                  const Icon = RESOURCE_ICON[r.kind] ?? ExternalLink;
                  return (
                    <li key={r.url}>
                      <a href={r.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] text-ink-2 hover:bg-surface-2 hover:text-ink">
                        <Icon className="size-4 shrink-0 text-ink-3" />
                        <span className="flex-1 truncate">{r.title ?? formatLabel(r.kind)}</span>
                        <ExternalLink className="size-3.5 text-ink-4" />
                      </a>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          <div className={cn("rounded-xl border border-dashed border-line-strong p-4 text-[12px] leading-relaxed text-ink-3")}>
            <p className="mb-1 font-medium text-ink-2">Source & provenance</p>
            Official {s.source.system} record #{s.source.source_id}, ingested {s.source.ingested_at ? new Date(s.source.ingested_at).toLocaleString() : "n/a"} (version {s.source.ingestion_version}). Format derived from{" "}
            {s.format_origin === "category" ? "the session's track" : s.format_origin === "title_pattern" ? "the session title" : s.format_origin}.{" "}
            {conference.schedule_url && (
              <a href={conference.schedule_url} target="_blank" rel="noopener noreferrer" className="text-ink-2 underline hover:text-ink">
                Official schedule
              </a>
            )}
          </div>
        </aside>
      </div>
    </article>
  );
}
