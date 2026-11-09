"use client";

import { ArrowRight, Compass, Sparkles, Telescope } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { AgendaPreview, Insights, Pathways } from "@/components/recommendations/dashboard-panels";
import { IntentComposer } from "@/components/recommendations/intent-composer";
import { ProfilePanel } from "@/components/recommendations/profile-panel";
import { RecommendationCard, RecommendationRow } from "@/components/recommendations/recommendation-card";
import { TIER_COPY } from "@/components/sessions/session-parts";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { useProfile, useRecommendations } from "@/hooks/use-data";
import { formatDateRange } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { InterestProfile, RecommendationResponse } from "@/types/api";

function hasProfile(p: InterestProfile | null | undefined): p is InterestProfile {
  return !!p && (p.primary_interests.length > 0 || p.learning_goals.length > 0 || !!p.intent_text);
}

function TierHeading({ tier, count, description }: { tier: keyof typeof TIER_COPY; count: number; description: string }) {
  const t = TIER_COPY[tier];
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <div className="flex items-baseline gap-2.5">
        <span className={cn("size-2 translate-y-[-2px] rounded-full", t.dot)} />
        <h2 className="text-[17px] font-semibold tracking-tight">{t.label}</h2>
        <span className="font-mono text-[12px] text-ink-3">{count}</span>
      </div>
      <p className="hidden text-[12.5px] text-ink-3 md:block">{description}</p>
    </div>
  );
}

function Recommendations({ data }: { data: RecommendationResponse }) {
  const total = data.must_attend.length + data.highly_relevant.length + data.explore.length;
  if (total === 0) {
    return (
      <EmptyState
        icon={Telescope}
        title="No strong matches yet"
        description="Try describing your goals in more detail, or add topics to your profile."
      />
    );
  }
  return (
    <div className="space-y-10">
      {data.must_attend.length > 0 && (
        <section aria-label="Must attend">
          <TierHeading tier="must_attend" count={data.must_attend.length} description="Closest to everything you described" />
          <div className="grid gap-4 md:grid-cols-2">
            {data.must_attend.slice(0, 4).map((r, i) => (
              <RecommendationCard key={r.session.id} rec={r} weights={data.weights} index={i} />
            ))}
          </div>
          {data.must_attend.length > 4 && (
            <div className="card mt-4 divide-y divide-line overflow-hidden">
              {data.must_attend.slice(4).map((r) => (
                <RecommendationRow key={r.session.id} rec={r} />
              ))}
            </div>
          )}
        </section>
      )}
      {data.highly_relevant.length > 0 && (
        <section aria-label="Highly relevant">
          <TierHeading tier="highly_relevant" count={data.highly_relevant.length} description="Strong matches worth fitting in" />
          <div className="card divide-y divide-line overflow-hidden">
            {data.highly_relevant.slice(0, 8).map((r) => (
              <RecommendationRow key={r.session.id} rec={r} />
            ))}
          </div>
          {data.highly_relevant.length > 8 && (
            <Link href="/recommendations?tier=highly_relevant" className="mt-3 inline-flex items-center gap-1 text-[12.5px] text-ink-2 hover:text-ink">
              See all {data.highly_relevant.length} <ArrowRight className="size-3.5" />
            </Link>
          )}
        </section>
      )}
      {data.explore.length > 0 && (
        <section aria-label="Explore">
          <TierHeading tier="explore" count={data.explore.length} description="Adjacent ideas the knowledge graph surfaced" />
          <div className="grid gap-4 md:grid-cols-2">
            {data.explore.slice(0, 4).map((r, i) => (
              <RecommendationCard key={r.session.id} rec={r} weights={data.weights} index={i} />
            ))}
          </div>
        </section>
      )}
      <p className="text-[12px] text-ink-4">
        {String(data.pipeline.retrieved)} sessions retrieved with Elasticsearch hybrid search, {String(data.pipeline.graph_expanded)} added by
        knowledge-graph expansion, {String(data.pipeline.scored)} ranked in {String(data.pipeline.took_ms)} ms.
        {data.degraded.length > 0 && ` Running in reduced mode: ${data.degraded.join(", ")}.`}
      </p>
    </div>
  );
}

function RecommendationsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-6 w-40" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-[380px]" />
        <Skeleton className="h-[380px]" />
      </div>
      <Skeleton className="h-48" />
    </div>
  );
}

export default function DiscoverPage() {
  const { conference, isLoading: confLoading, error: confError, refetch: refetchConf } = useConference();
  const profileQ = useProfile();
  const profile = profileQ.data;
  const active = hasProfile(profile);
  const recs = useRecommendations(undefined, active);
  const [refining, setRefining] = React.useState(false);

  if (confError) {
    return (
      <div className="mx-auto max-w-xl pt-16">
        <ErrorState error={confError} onRetry={refetchConf} />
        <p className="mt-3 text-[13px] text-ink-3">
          The API is reachable at <code className="font-mono">NEXT_PUBLIC_API_URL</code>. Make sure the backend is running and data has been ingested
          (<code className="font-mono">make ingest</code>).
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <section className="pt-2">
        <div className="eyebrow mb-3 flex flex-wrap items-center gap-x-2 gap-y-1">
          <Compass className="size-3 text-needle" />
          {confLoading || !conference ? (
            <Skeleton className="h-3 w-64" />
          ) : (
            <span>
              {conference.short_name} · {conference.city.split(",")[0]} · {formatDateRange(conference.start_date, conference.end_date)} ·{" "}
              {conference.content_session_count} sessions · {conference.speaker_count} speakers
            </span>
          )}
        </div>
        <div className="grid items-end gap-6 lg:grid-cols-[1fr_auto]">
          <div className="max-w-3xl">
            <h1 className="font-display text-[40px] leading-[1.02] tracking-[-0.01em] text-ink sm:text-[52px]">
              {active ? (
                <>
                  Your bearings for <span className="italic text-needle-ink">this week</span>
                </>
              ) : (
                <>
                  What do you want to <span className="italic text-needle-ink">learn</span> at KubeCon?
                </>
              )}
            </h1>
            <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-2">
              {active
                ? "Ranked from the official schedule with Elasticsearch hybrid search and the conference knowledge graph. Every match explains itself."
                : "Describe what you're building. KubeCompass finds the sessions, speakers and technologies that matter, explains why, and helps you plan your agenda."}
            </p>
          </div>
          {active && !refining && (
            <Button variant="secondary" onClick={() => setRefining(true)}>
              <Sparkles /> Describe it differently
            </Button>
          )}
        </div>
        {(!active || refining) && (
          <div className="mt-6 max-w-3xl">
            <IntentComposer initial={profile?.intent_text} compact={active} onParsed={() => setRefining(false)} />
          </div>
        )}
      </section>

      {profileQ.isLoading ? (
        <RecommendationsSkeleton />
      ) : active ? (
        <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0">
            {recs.isLoading && <RecommendationsSkeleton />}
            {recs.isError && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
            {recs.data && <Recommendations data={recs.data} />}
          </div>
          <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
            <ProfilePanel profile={profile} />
            <AgendaPreview />
            {recs.data && <Insights data={recs.data} />}
          </aside>
        </div>
      ) : null}

      <div className={cn(active && "border-t border-line pt-10")}>
        <Pathways />
      </div>
    </div>
  );
}
