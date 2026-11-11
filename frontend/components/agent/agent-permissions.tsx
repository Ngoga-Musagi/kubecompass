"use client";

import { Check, Lock, ShieldCheck } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AgentPermission, AgentStatus } from "@/types/api";

/** Choose what the agent may do. Read is implied; unavailable levels are shown, not grantable. */
export function PermissionChooser({
  status,
  value,
  onChange,
}: {
  status: AgentStatus;
  value: AgentPermission[];
  onChange: (next: AgentPermission[]) => void;
}) {
  return (
    <ul className="space-y-2" aria-label="Agent permissions">
      {status.catalog.map((p) => {
        const always = p.id === "read";
        const checked = always || value.includes(p.id);
        const id = `perm-${p.id}`;
        return (
          <li
            key={p.id}
            className={cn(
              "flex gap-3 rounded-xl border p-3 transition-colors",
              checked && p.available ? "border-needle/40 bg-needle-soft/40" : "border-line bg-surface",
              !p.available && "opacity-70",
            )}
          >
            <input
              id={id}
              type="checkbox"
              className="mt-0.5 size-4 shrink-0 accent-[var(--needle)]"
              checked={checked}
              disabled={always || !p.available}
              onChange={(e) => onChange(e.target.checked ? [...value, p.id] : value.filter((x) => x !== p.id))}
            />
            <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
              <span className="flex items-center gap-1.5 text-[13.5px] font-medium text-ink">
                {p.title}
                {always && <span className="text-[11px] font-normal text-ink-3">· always on</span>}
                {!p.available && <Lock className="size-3 text-ink-4" aria-hidden />}
              </span>
              <span className="mt-0.5 block text-[12.5px] leading-relaxed text-ink-3">
                {p.available ? p.description : p.unavailable_reason}
              </span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

/** First run: explain the agent, pick permissions, enable. */
export function AgentSetup({
  status,
  eventName,
  onEnable,
  busy,
}: {
  status: AgentStatus;
  eventName: string;
  onEnable: (permissions: AgentPermission[]) => void;
  busy: boolean;
}) {
  const [perms, setPerms] = React.useState<AgentPermission[]>(["personalization", "agenda"]);
  return (
    <section aria-labelledby="agent-setup" className="mx-auto max-w-xl py-6">
      <div className="eyebrow mb-3 flex items-center gap-1.5">
        <ShieldCheck className="size-3 text-needle" /> Your event agent
      </div>
      <h1 id="agent-setup" className="font-display text-[34px] leading-tight sm:text-[40px]">
        Your companion for {eventName}
      </h1>
      <p className="mt-2 text-[14.5px] text-ink-2">
        It finds sessions and people for your goals, plans a conflict-free agenda, and tells you where to be next, by text or voice.
        It only uses this event&apos;s official data, and you decide what it may do.
      </p>
      <div className="mt-6">
        <PermissionChooser status={status} value={perms} onChange={setPerms} />
      </div>
      <ul className="mt-4 space-y-1.5 text-[12.5px] text-ink-3">
        {[
          "It works only within this event.",
          "It asks before every change to your agenda.",
          "You can change these choices, clear what it knows, or turn it off at any time.",
        ].map((t) => (
          <li key={t} className="flex gap-2">
            <Check className="mt-0.5 size-3.5 shrink-0 text-ok" /> {t}
          </li>
        ))}
      </ul>
      <Button variant="accent" size="lg" className="mt-6 w-full sm:w-auto" disabled={busy} onClick={() => onEnable(perms)}>
        {busy ? "Enabling…" : "Enable my agent"}
      </Button>
    </section>
  );
}
