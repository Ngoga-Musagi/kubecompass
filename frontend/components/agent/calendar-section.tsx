"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CalendarSync, Link2, Loader2, Unlink } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import type { AgentPermission, AgentStatus } from "@/types/api";

/** Plain-language reasons for a failed Google connection (codes from the OAuth callback). */
export const CALENDAR_ERRORS: Record<string, string> = {
  scope_denied:
    "Google didn't give conCompass calendar access. Connect again, and on Google's screen tick the box that allows conCompass to view and edit events on your calendars.",
  cancelled: "Google sign-in was cancelled, so nothing was connected.",
  exchange_failed: "Google didn't accept the sign-in. Try connecting again; if it keeps failing, the app's Google settings need checking.",
  expired_state: "The Google sign-in took too long. Please connect again.",
  bad_state: "The Google sign-in link wasn't valid. Please connect again.",
  permission_required: "“Connect external accounts” was turned off during sign-in. Connect again to allow it.",
  not_configured: "Google Calendar isn't set up on this server yet.",
};

function lastSyncText(s: AgentStatus["calendar"]["last_sync"]): string | null {
  if (!s) return null;
  const parts = [
    s.created && `${s.created} added`,
    s.updated && `${s.updated} updated`,
    s.deleted && `${s.deleted} removed`,
    s.unchanged && `${s.unchanged} up to date`,
    s.failed && `${s.failed} failed`,
  ].filter(Boolean);
  return `Last sync ${new Date(s.at).toLocaleString()}: ${parts.join(", ") || "nothing to sync"}.`;
}

/** Google Calendar: connect (OAuth), pick a calendar, sync (one click or automatic), disconnect. */
export function CalendarSection({
  status,
  pending,
  notice,
}: {
  status: AgentStatus;
  pending: AgentPermission[];
  notice?: string | null;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const cal = status.calendar;
  const refresh = () => qc.invalidateQueries({ queryKey: ["agent"] });
  const fail = (e: unknown) => toast({ tone: "error", title: e instanceof ApiError ? e.message : "Something went wrong. Try again." });
  const withPerm = (p: AgentPermission) => Array.from(new Set<AgentPermission>([...status.permissions, ...pending, p]));

  const connect = useMutation({
    mutationFn: async () => {
      // Clicking Connect is the explicit grant of "Connect external accounts" for this event.
      if (!status.permissions.includes("integrations")) await api.setAgent(true, withPerm("integrations"));
      return api.calendarConnect();
    },
    onSuccess: ({ auth_url }) => {
      window.location.href = auth_url;
    },
    onError: fail,
  });
  const calendars = useQuery({
    queryKey: ["calendars", status.conference_id],
    queryFn: api.calendars,
    enabled: cal.connected && status.permissions.includes("integrations"),
  });
  const choose = useMutation({ mutationFn: api.chooseCalendar, onSuccess: () => void refresh(), onError: fail });
  const canSync = status.permissions.includes("external_actions");
  const sync = useMutation({
    mutationFn: async () => {
      // "Allow & sync": the click grants "Act outside conCompass" and confirms this sync.
      if (!canSync) await api.setAgent(true, withPerm("external_actions"));
      return api.agentAction("sync_agenda_to_calendar", {});
    },
    onSuccess: (r) => {
      toast({ tone: "success", title: r.reply });
      void refresh();
    },
    onError: fail,
  });
  const autosync = useMutation({
    mutationFn: (on: boolean) => api.setAgent(true, status.permissions, on),
    onSuccess: (s) => {
      qc.setQueryData(["agent", s.conference_id], s);
      toast({
        tone: "success",
        title: s.calendar_autosync ? "Your calendar will stay up to date" : "Automatic sync turned off",
        description: s.calendar_autosync ? "Sessions you save or remove are synced automatically." : undefined,
      });
      if (s.calendar_autosync) setTimeout(() => void refresh(), 4000); // first sync runs now
    },
    onError: fail,
  });
  const disconnect = useMutation({
    mutationFn: api.disconnectCalendar,
    onSuccess: () => {
      toast({ tone: "info", title: "Google Calendar disconnected", description: "Access was revoked at Google." });
      void refresh();
    },
    onError: fail,
  });

  const sessions = `${status.agenda_count} saved session${status.agenda_count === 1 ? "" : "s"}`;
  return (
    <section className="mt-6 rounded-xl border border-line p-3" aria-labelledby="gcal-title">
      <p id="gcal-title" className="flex items-center gap-1.5 text-[13px] font-medium">
        <CalendarSync className="size-4 text-needle" /> Google Calendar
      </p>
      {notice && !cal.connected && (
        <p role="alert" className="mt-2 flex gap-2 rounded-lg border border-warn/30 bg-warn-soft/60 p-2.5 text-[12.5px] text-ink-2">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" /> {notice}
        </p>
      )}
      {!cal.configured ? (
        <p className="mt-1 text-[12.5px] text-ink-3">
          Not set up on this server yet. You can still download your agenda as a calendar file from My Agenda.
        </p>
      ) : !cal.connected ? (
        <>
          <p className="mt-1 text-[12.5px] text-ink-3">
            Put your saved sessions straight into your calendar. conCompass only gets access to calendar events and your list of
            calendars, and only writes what you sync. On Google&apos;s screen, tick the box that allows calendar access.
          </p>
          <Button className="mt-3" size="sm" variant="accent" onClick={() => connect.mutate()} disabled={connect.isPending}>
            {connect.isPending ? <Loader2 className="animate-spin" /> : <Link2 />} Connect Google Calendar
          </Button>
        </>
      ) : (
        <div className="mt-2 space-y-3">
          <label className="block text-[12.5px] text-ink-2">
            Sync to
            <select
              className="mt-1 block h-9 w-full rounded-lg border border-line bg-bg px-2 text-[13px] text-ink"
              value={cal.calendar_id ?? ""}
              disabled={choose.isPending || !calendars.data}
              onChange={(e) => choose.mutate(e.target.value)}
              aria-label="Calendar to sync to"
            >
              {calendars.data ? (
                calendars.data.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.primary ? " (primary)" : ""}
                  </option>
                ))
              ) : (
                <option value={cal.calendar_id ?? ""}>{cal.calendar_name}</option>
              )}
            </select>
          </label>
          {status.agenda_count === 0 ? (
            <p className="rounded-lg bg-surface-2 p-2.5 text-[12.5px] text-ink-2">
              Your agenda is empty, so there&apos;s nothing to put in your calendar yet. Save sessions from{" "}
              <Link href="/recommendations" className="font-medium text-needle-ink hover:underline">
                Recommendations
              </Link>{" "}
              or ask your agent to “Build my agenda for Wednesday”.
            </p>
          ) : (
            <p className="text-[12.5px] text-ink-2">
              {sessions} will go to “{cal.calendar_name}” in event time ({status.calendar.synced_sessions} synced so far).
            </p>
          )}
          {cal.last_sync && <p className="text-[12px] text-ink-3">{lastSyncText(cal.last_sync)}</p>}
          {cal.last_sync?.failed ? (
            <p role="alert" className="flex gap-2 rounded-lg border border-warn/30 bg-warn-soft/60 p-2.5 text-[12.5px] text-ink-2">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" />
              <span>
                {cal.last_sync.failed} couldn&apos;t be synced
                {cal.last_sync.error ? `: ${cal.last_sync.error}` : "."} Syncing again retries them.
              </span>
            </p>
          ) : null}
          {calendars.isError && (
            <p className="text-[12px] text-warn">{calendars.error instanceof ApiError ? calendars.error.message : "Couldn't load your calendars."}</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="accent" disabled={sync.isPending || status.agenda_count === 0} onClick={() => sync.mutate()}>
              {sync.isPending ? <Loader2 className="animate-spin" /> : <CalendarSync />}
              {canSync ? "Sync my agenda now" : "Allow & sync my agenda now"}
            </Button>
            <Button size="sm" variant="danger" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
              <Unlink /> Disconnect
            </Button>
          </div>
          {!canSync && (
            <p className="text-[11.5px] text-ink-4">Syncing also allows “Act outside conCompass” for this event; you can turn it off above.</p>
          )}
          <label className="flex items-start gap-2.5 rounded-lg border border-line p-2.5">
            <input
              type="checkbox"
              className="mt-0.5 size-4 accent-[var(--needle)]"
              checked={status.calendar_autosync}
              disabled={!canSync || autosync.isPending}
              onChange={(e) => autosync.mutate(e.target.checked)}
            />
            <span className="text-[12.5px]">
              <span className="font-medium text-ink">Keep my calendar updated automatically</span>
              <span className="block text-ink-3">
                {canSync
                  ? "Sessions you save or remove, here or through your agent, are synced without asking again."
                  : "Available after your first sync."}
              </span>
            </span>
          </label>
        </div>
      )}
    </section>
  );
}
