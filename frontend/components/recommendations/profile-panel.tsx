"use client";

import { useQuery } from "@tanstack/react-query";
import { Ban, GraduationCap, Pencil, Plus, Search, Sparkles, Target, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Badge, Tooltip } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/sheet";
import { useSaveProfile } from "@/hooks/use-data";
import { api } from "@/lib/api";
import { formatLabel } from "@/lib/format";
import { cn, entityColor } from "@/lib/utils";
import type { ExperienceLevel, InterestProfile, ProfileInterest } from "@/types/api";

const FORMAT_OPTIONS = ["talk", "demo", "tutorial", "lightning_talk", "keynote", "panel", "contribfest", "poster", "birds_of_a_feather"];
const LEVELS: ExperienceLevel[] = ["any", "beginner", "intermediate", "advanced"];

function InterestChip({ item, onRemove, tone = "primary" }: { item: ProfileInterest; onRemove?: () => void; tone?: "primary" | "secondary" | "excluded" }) {
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-full border pl-2.5 text-[12.5px]",
        onRemove ? "pr-1" : "pr-2.5",
        tone === "primary" && "border-line-strong bg-surface text-ink",
        tone === "secondary" && "border-line bg-surface-2/60 text-ink-2",
        tone === "excluded" && "border-danger/25 bg-danger-soft/50 text-ink-2 line-through decoration-danger/50",
      )}
    >
      <span className="size-1.5 rounded-full" style={{ background: item.type ? entityColor(item.type) : "var(--ink-4)" }} />
      {item.label}
      {onRemove && (
        <button onClick={onRemove} className="rounded-full p-0.5 text-ink-3 hover:bg-surface-3 hover:text-ink" aria-label={`Remove ${item.label}`}>
          <X className="size-3" />
        </button>
      )}
    </span>
  );
}

export function ProfilePanel({ profile, llmUsed }: { profile: InterestProfile; llmUsed?: boolean }) {
  const [editing, setEditing] = React.useState(false);
  return (
    <section className="card p-5" aria-labelledby="profile-title">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="eyebrow mb-1 flex items-center gap-1.5">
            <Sparkles className="size-3" /> Your interest profile
          </div>
          <h2 id="profile-title" className="text-[15px] font-semibold text-ink">
            What KubeCompass understood
          </h2>
          <p className="mt-0.5 text-[12px] text-ink-3">
            {profile.parser === "llm" || llmUsed
              ? "Interpreted with AI and grounded in this conference's topics."
              : profile.parser === "manual"
                ? "Edited by you."
                : "Matched against this conference's topics and technologies."}
          </p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
          <Pencil /> Edit
        </Button>
      </div>

      <div className="space-y-4">
        <div>
          <p className="eyebrow mb-2">Main interests</p>
          {profile.primary_interests.length ? (
            <div className="flex flex-wrap gap-1.5">
              {profile.primary_interests.map((i) => (
                <InterestChip key={i.entity_id ?? i.label} item={i} />
              ))}
            </div>
          ) : (
            <p className="text-[13px] text-ink-3">None detected yet. Add some with Edit.</p>
          )}
        </div>
        {profile.secondary_interests.length > 0 && (
          <div>
            <p className="eyebrow mb-2">Related areas</p>
            <div className="flex flex-wrap gap-1.5">
              {profile.secondary_interests.map((i) => (
                <InterestChip key={i.entity_id ?? i.label} item={i} tone="secondary" />
              ))}
            </div>
          </div>
        )}
        {profile.learning_goals.length > 0 && (
          <div>
            <p className="eyebrow mb-2">Learning goals</p>
            <ul className="space-y-1.5">
              {profile.learning_goals.map((g) => (
                <li key={g} className="flex gap-2 text-[13px] leading-snug text-ink-2">
                  <Target className="mt-0.5 size-3.5 shrink-0 text-needle" />
                  {g}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          <Tooltip content="Experience level used to weigh audience level">
            <span>
              <Badge tone="outline" className="capitalize">
                <GraduationCap /> {profile.experience_level === "any" ? "Any level" : profile.experience_level}
              </Badge>
            </span>
          </Tooltip>
          {profile.preferred_formats.map((f) => (
            <Badge key={f} tone="neutral">
              {formatLabel(f)}
            </Badge>
          ))}
          {profile.excluded_topics.map((x) => (
            <Badge key={x.label} tone="danger">
              <Ban /> {x.label}
            </Badge>
          ))}
        </div>
      </div>
      <ProfileEditor open={editing} onOpenChange={setEditing} profile={profile} />
    </section>
  );
}

function EntityPicker({ onPick, placeholder }: { onPick: (i: ProfileInterest) => void; placeholder: string }) {
  const [q, setQ] = React.useState("");
  const { data } = useQuery({
    queryKey: ["entity-picker", q],
    queryFn: () => api.graphSearch(q),
    enabled: q.trim().length >= 2,
  });
  const options = (data?.entities ?? []).filter((e) => ["topic", "technology", "project"].includes(e.type));
  return (
    <div className="relative">
      <div className="flex h-9 items-center gap-2 rounded-[10px] border border-line bg-surface px-2.5 focus-within:border-ink/40">
        <Search className="size-4 text-ink-3" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-ink-4" />
      </div>
      {q.trim().length >= 2 && (
        <ul className="absolute inset-x-0 top-10 z-10 max-h-56 overflow-auto rounded-xl border border-line bg-surface p-1 shadow-[var(--shadow-lg)]">
          {options.length === 0 && <li className="px-3 py-2 text-[12.5px] text-ink-3">No matching topics in this conference.</li>}
          {options.map((o) => (
            <li key={o.id}>
              <button
                onClick={() => {
                  onPick({ label: o.name, entity_id: o.id, type: o.type });
                  setQ("");
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] hover:bg-surface-2"
              >
                <span className="size-1.5 rounded-full" style={{ background: entityColor(o.type) }} />
                <span className="flex-1">{o.name}</span>
                <span className="text-[11.5px] text-ink-3">{o.session_count} sessions</span>
                <Plus className="size-3.5 text-ink-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ProfileEditor({ open, onOpenChange, profile }: { open: boolean; onOpenChange: (o: boolean) => void; profile: InterestProfile }) {
  const [draft, setDraft] = React.useState(profile);
  const [goal, setGoal] = React.useState("");
  const save = useSaveProfile();
  React.useEffect(() => {
    if (open) setDraft(profile);
  }, [open, profile]);

  const without = (list: ProfileInterest[], x: ProfileInterest) => list.filter((i) => (i.entity_id ?? i.label) !== (x.entity_id ?? x.label));
  const addUnique = (list: ProfileInterest[], x: ProfileInterest) => (list.some((i) => i.entity_id === x.entity_id) ? list : [...list, x]);

  const commit = () => {
    const primary = draft.primary_interests;
    save.mutate(
      {
        ...draft,
        parser: "manual",
        preferred_topics: primary.filter((p) => p.type === "topic"),
        preferred_technologies: primary.filter((p) => p.type === "technology" || p.type === "project"),
      },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Edit your interest profile"
      description="Recommendations update as soon as you save."
      footer={
        <div className="flex items-center justify-between gap-2">
          {save.isError ? <span className="text-[12.5px] text-danger">Couldn&apos;t save. Try again.</span> : <span />}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={commit} disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save profile"}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-6">
        <section>
          <p className="eyebrow mb-2">Main interests</p>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {draft.primary_interests.map((i) => (
              <InterestChip key={i.entity_id ?? i.label} item={i} onRemove={() => setDraft({ ...draft, primary_interests: without(draft.primary_interests, i) })} />
            ))}
          </div>
          <EntityPicker placeholder="Add a topic, technology or project…" onPick={(i) => setDraft({ ...draft, primary_interests: addUnique(draft.primary_interests, i), excluded_topics: without(draft.excluded_topics, i) })} />
        </section>
        <section>
          <p className="eyebrow mb-2">Related areas</p>
          <div className="flex flex-wrap gap-1.5">
            {draft.secondary_interests.length === 0 && <p className="text-[12.5px] text-ink-3">None.</p>}
            {draft.secondary_interests.map((i) => (
              <InterestChip key={i.entity_id ?? i.label} item={i} tone="secondary" onRemove={() => setDraft({ ...draft, secondary_interests: without(draft.secondary_interests, i) })} />
            ))}
          </div>
        </section>
        <section>
          <p className="eyebrow mb-2">Learning goals</p>
          <ul className="mb-2 space-y-1.5">
            {draft.learning_goals.map((g) => (
              <li key={g} className="flex items-start gap-2 rounded-lg bg-surface-2/70 px-2.5 py-1.5 text-[13px] text-ink-2">
                <span className="flex-1">{g}</span>
                <button onClick={() => setDraft({ ...draft, learning_goals: draft.learning_goals.filter((x) => x !== g) })} aria-label="Remove goal" className="text-ink-3 hover:text-ink">
                  <X className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (goal.trim()) setDraft({ ...draft, learning_goals: [...draft.learning_goals, goal.trim()].slice(0, 10) });
              setGoal("");
            }}
            className="flex gap-2"
          >
            <input value={goal} onChange={(e) => setGoal(e.target.value)} maxLength={300} placeholder="e.g. Run LLM inference cost-effectively" className="h-9 flex-1 rounded-[10px] border border-line bg-surface px-2.5 text-[13px] outline-none focus:border-ink/40" />
            <Button type="submit" size="md">
              Add
            </Button>
          </form>
        </section>
        <section>
          <p className="eyebrow mb-2">Preferred formats</p>
          <div className="flex flex-wrap gap-1.5">
            {FORMAT_OPTIONS.map((f) => {
              const on = draft.preferred_formats.includes(f);
              return (
                <button
                  key={f}
                  aria-pressed={on}
                  onClick={() => setDraft({ ...draft, preferred_formats: on ? draft.preferred_formats.filter((x) => x !== f) : [...draft.preferred_formats, f] })}
                  className={cn("h-7 rounded-full border px-3 text-[12.5px] transition-colors", on ? "border-ink bg-ink text-bg" : "border-line bg-surface text-ink-2 hover:border-line-strong")}
                >
                  {formatLabel(f)}
                </button>
              );
            })}
          </div>
        </section>
        <section>
          <p className="eyebrow mb-2">Experience level</p>
          <div className="flex flex-wrap gap-1.5">
            {LEVELS.map((l) => (
              <button
                key={l}
                aria-pressed={draft.experience_level === l}
                onClick={() => setDraft({ ...draft, experience_level: l })}
                className={cn("h-7 rounded-full border px-3 text-[12.5px] capitalize transition-colors", draft.experience_level === l ? "border-ink bg-ink text-bg" : "border-line bg-surface text-ink-2 hover:border-line-strong")}
              >
                {l === "any" ? "Any level" : l}
              </button>
            ))}
          </div>
        </section>
        <section>
          <p className="eyebrow mb-2">Not interested in</p>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {draft.excluded_topics.map((i) => (
              <InterestChip key={i.entity_id ?? i.label} item={i} tone="excluded" onRemove={() => setDraft({ ...draft, excluded_topics: without(draft.excluded_topics, i) })} />
            ))}
          </div>
          <EntityPicker placeholder="Exclude a topic…" onPick={(i) => setDraft({ ...draft, excluded_topics: addUnique(draft.excluded_topics, i), primary_interests: without(draft.primary_interests, i) })} />
        </section>
      </div>
    </Sheet>
  );
}
