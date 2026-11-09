"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Network } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { EntityChip, OriginBadge } from "@/components/sessions/session-parts";
import { SessionCard } from "@/components/sessions/session-card";
import { Avatar, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { api } from "@/lib/api";
import { speakerHref } from "@/lib/format";

const LINK_LABEL: Record<string, string> = { linkedin: "LinkedIn", twitter: "X / Twitter", blog: "Blog", company_website: "Company", sessionize: "Sessionize", other: "Website" };

export default function SpeakerPage() {
  const { id } = useParams<{ id: string }>();
  const sid = decodeURIComponent(id);
  const { conference } = useConference();
  const q = useQuery({ queryKey: ["speaker", sid], queryFn: () => api.speaker(sid), enabled: !!conference });
  if (q.isLoading || !conference) return <Skeleton className="h-96" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data!;
  return (
    <div className="animate-fade">
      <Link href="/speakers" className="mb-5 inline-flex items-center gap-1 text-[12.5px] text-ink-3 hover:text-ink">
        <ArrowLeft className="size-3.5" /> All speakers
      </Link>
      <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-5">
            <Avatar name={s.full_name} src={s.photo_url} size={88} />
            <div className="min-w-0">
              <h1 className="font-display text-[40px] leading-tight">{s.full_name}</h1>
              <p className="text-[14px] text-ink-2">{[s.job_title, s.company].filter(Boolean).join(" · ") || s.tagline}</p>
            </div>
          </div>
          {s.bio ? (
            <p className="mt-6 max-w-3xl whitespace-pre-line text-[15px] leading-[1.7] text-ink-2">{s.bio}</p>
          ) : (
            <p className="mt-6 text-[14px] text-ink-3">No bio was published.</p>
          )}
          <h2 className="eyebrow mb-3 mt-10">Sessions at {conference.short_name}</h2>
          <div className="space-y-3">
            {s.sessions.map((x) => (
              <SessionCard key={x.id} session={x} />
            ))}
          </div>
        </div>
        <aside className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          {(s.works_on.length > 0 || s.expertise.length > 0) && (
            <div className="card space-y-4 p-4">
              <h2 className="eyebrow flex items-center gap-1.5">
                <Network className="size-3" /> Expertise signals
              </h2>
              {s.works_on.length > 0 && (
                <div>
                  <p className="mb-2 text-[12.5px] text-ink-3">Works on</p>
                  <ul className="space-y-2">
                    {s.works_on.map((e) => (
                      <li key={e.id} className="flex flex-wrap items-center gap-2">
                        <EntityChip entity={e} />
                        <OriginBadge origin={e.origin} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {s.expertise.length > 0 && (
                <div>
                  <p className="mb-2 text-[12.5px] text-ink-3">Mentioned in bio</p>
                  <div className="flex flex-wrap gap-1.5">
                    {s.expertise.map((e) => (
                      <EntityChip key={e.id} entity={e} />
                    ))}
                  </div>
                </div>
              )}
              <p className="text-[11.5px] leading-relaxed text-ink-4">Derived from the speaker&apos;s published bio and sessions. Hover a topic to see the evidence.</p>
            </div>
          )}
          {s.related_speakers.length > 0 && (
            <div className="card p-4">
              <h2 className="eyebrow mb-3">Co-presenters</h2>
              <ul className="space-y-2.5">
                {s.related_speakers.map((r) => (
                  <li key={r.id}>
                    <Link href={speakerHref(r.id)} className="flex items-center gap-2.5 hover:underline">
                      <Avatar name={r.full_name} src={r.photo_url} size={28} />
                      <span className="min-w-0 truncate text-[13px] text-ink">{r.full_name}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {s.links.length > 0 && (
            <div className="card p-4">
              <h2 className="eyebrow mb-2">Links</h2>
              {s.links.map((l) => (
                <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between rounded-lg px-2 py-1.5 text-[13px] text-ink-2 hover:bg-surface-2 hover:text-ink">
                  {LINK_LABEL[l.kind] ?? l.title ?? l.kind}
                  <ExternalLink className="size-3.5 text-ink-4" />
                </a>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
