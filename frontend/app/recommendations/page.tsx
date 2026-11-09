"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { ProfilePanel } from "@/components/recommendations/profile-panel";
import { RecommendationCard } from "@/components/recommendations/recommendation-card";
import { TIER_COPY } from "@/components/sessions/session-parts";
import { EmptyState, ErrorState, Segmented, Skeleton } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { useProfile, useRecommendations } from "@/hooks/use-data";
import { formatDay, formatLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Recommendation, Tier } from "@/types/api";

type TierFilter = Tier | "all";

function Inner() {
  const params = useSearchParams();
  const router = useRouter();
  const { conference } = useConference();
  const profile = useProfile();
  const tier = (params.get("tier") as TierFilter) || "all";
  const day = params.get("day") ?? "";
  const format = params.get("format") ?? "";
  const filters = { days: day ? [day] : [], formats: format ? [format] : [] };
  const active = !!profile.data && (profile.data.primary_interests.length > 0 || !!profile.data.intent_text);
  const recs = useRecommendations(filters, active);

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params.toString());
    if (v) p.set(k, v);
    else p.delete(k);
    router.replace(`/recommendations?${p.toString()}`, { scroll: false });
  };

  if (profile.isLoading) return <Skeleton className="h-96" />;
  if (!active) {
    return (
      <EmptyState
        icon={Sparkles}
        title="Tell KubeCompass what you want to learn"
        description="Recommendations are built from your interest profile."
        action={
          <Link href="/" className="inline-flex h-9 items-center rounded-[10px] bg-ink px-3.5 text-[13px] font-medium text-bg">
            Start on Discover
          </Link>
        }
      />
    );
  }
  const data = recs.data;
  const lists: [Tier, Recommendation[]][] = data
    ? [
        ["must_attend", data.must_attend],
        ["highly_relevant", data.highly_relevant],
        ["explore", data.explore],
      ]
    : [];
  const shown = lists.filter(([t]) => tier === "all" || t === tier);

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        <div className="mb-6">
          <div className="eyebrow mb-2">Recommendations</div>
          <h1 className="font-display text-[38px] leading-tight">Everything ranked for you</h1>
          <p className="mt-1 text-[14px] text-ink-3">Filters narrow the candidates before ranking; relevance never changes because of agenda conflicts.</p>
        </div>
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <Segmented<TierFilter>
            label="Tier"
            value={tier}
            onChange={(v) => set("tier", v === "all" ? "" : v)}
            options={[
              { value: "all", label: "All" },
              { value: "must_attend", label: TIER_COPY.must_attend.label },
              { value: "highly_relevant", label: TIER_COPY.highly_relevant.label },
              { value: "explore", label: TIER_COPY.explore.label },
            ]}
          />
          <select value={day} onChange={(e) => set("day", e.target.value)} className="h-8 rounded-[10px] border border-line bg-surface px-2 text-[12.5px] text-ink-2" aria-label="Day">
            <option value="">All days</option>
            {conference?.days.map((d) => (
              <option key={d} value={d}>
                {formatDay(d, "long")}
              </option>
            ))}
          </select>
          <select value={format} onChange={(e) => set("format", e.target.value)} className="h-8 rounded-[10px] border border-line bg-surface px-2 text-[12.5px] text-ink-2" aria-label="Format">
            <option value="">All formats</option>
            {conference?.formats.map((f) => (
              <option key={f.value} value={f.value}>
                {formatLabel(f.value)} ({f.count})
              </option>
            ))}
          </select>
        </div>
        {recs.isLoading && <Skeleton className="h-[480px]" />}
        {recs.isError && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
        {data && shown.every(([, l]) => l.length === 0) && <EmptyState title="No recommendations with these filters" description="Try another day or format." />}
        <div className={cn("space-y-10", recs.isFetching && "opacity-70")}>
          {data &&
            shown.map(([t, list]) =>
              list.length ? (
                <section key={t}>
                  <h2 className="mb-3 flex items-center gap-2 text-[16px] font-semibold">
                    <span className={cn("size-2 rounded-full", TIER_COPY[t].dot)} /> {TIER_COPY[t].label}
                    <span className="font-mono text-[12px] font-normal text-ink-3">{list.length}</span>
                  </h2>
                  <div className="grid gap-4 md:grid-cols-2">
                    {list.map((r, i) => (
                      <RecommendationCard key={r.session.id} rec={r} weights={data.weights} index={i} />
                    ))}
                  </div>
                </section>
              ) : null,
            )}
        </div>
      </div>
      <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">{profile.data && <ProfilePanel profile={profile.data} />}</aside>
    </div>
  );
}

export default function RecommendationsPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96" />}>
      <Inner />
    </React.Suspense>
  );
}
