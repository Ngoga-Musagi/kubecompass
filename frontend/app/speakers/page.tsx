"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, Star, Users } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Avatar, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { api } from "@/lib/api";
import { speakerHref } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE = 36;

export default function SpeakersPage() {
  const { conference } = useConference();
  const [draft, setDraft] = React.useState("");
  const [q, setQ] = React.useState("");
  const [limit, setLimit] = React.useState(PAGE);
  React.useEffect(() => {
    const t = setTimeout(() => {
      setQ(draft.trim());
      setLimit(PAGE);
    }, 250);
    return () => clearTimeout(t);
  }, [draft]);

  const res = useQuery({
    queryKey: ["speakers", conference?.id, q, limit],
    queryFn: () => api.speakers({ q, limit }),
    enabled: !!conference,
    placeholderData: (p) => p,
  });

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow mb-2">Speakers</div>
          <h1 className="font-display text-[38px] leading-tight">Who&apos;s speaking</h1>
          <p className="mt-1 text-[14px] text-ink-3">
            {conference ? `${conference.speaker_count} speakers.` : ""} Search by name, company, or expertise. Results combine keyword and semantic matches over bios and talks.
          </p>
        </div>
        <div className="flex h-10 w-full max-w-sm items-center gap-2 rounded-xl border border-line-strong bg-surface px-3 focus-within:shadow-[0_0_0_4px_var(--ring)]">
          <Search className="size-4 text-ink-3" />
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. GPU scheduling, Google, eBPF" className="flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-4" aria-label="Search speakers" />
        </div>
      </div>
      {res.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-[132px]" />
          ))}
        </div>
      )}
      {res.isError && <ErrorState error={res.error} onRetry={() => res.refetch()} />}
      {res.data && res.data.items.length === 0 && <EmptyState icon={Users} title="No speakers match" description="Try a project, a company or a broader topic." />}
      {res.data && (
        <>
          <div className={cn("grid gap-3 sm:grid-cols-2 xl:grid-cols-3", res.isFetching && "opacity-70")}>
            {res.data.items.map((s) => (
              <Link key={s.id} href={speakerHref(s.id)} className="card flex min-w-0 gap-3 p-4 transition-[border-color,box-shadow] hover:border-line-strong hover:shadow-[var(--shadow-md)]">
                <Avatar name={s.full_name} src={s.photo_url} size={48} />
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1.5 truncate text-[14.5px] font-semibold text-ink">
                    {s.full_name}
                    {s.is_top_speaker && <Star className="size-3.5 shrink-0 fill-needle text-needle" aria-label="Top speaker on Sessionize" />}
                  </p>
                  <p className="truncate text-[12.5px] text-ink-3">{[s.job_title, s.company].filter(Boolean).join(" · ") || s.tagline || " "}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {s.expertise.slice(0, 3).map((e) => (
                      <span key={e.id} className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-2">
                        {e.name}
                      </span>
                    ))}
                  </div>
                  <p className="mt-2 font-mono text-[10.5px] uppercase tracking-wider text-ink-4">
                    {s.session_count} session{s.session_count === 1 ? "" : "s"}
                  </p>
                </div>
              </Link>
            ))}
          </div>
          {res.data.total > res.data.items.length && (
            <div className="mt-6 flex justify-center">
              <Button variant="secondary" onClick={() => setLimit((l) => l + PAGE)} disabled={res.isFetching}>
                Show more ({res.data.total - res.data.items.length} remaining)
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
