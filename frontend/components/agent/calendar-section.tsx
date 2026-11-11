"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarSync, Link2, Loader2, Unlink } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import type { AgentPermission, AgentStatus } from "@/types/api";

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

/** Google Calendar: connect (OAuth), pick a calendar, sync with one confirmed click, disconnect. */
export function CalendarSection({ status, pending }: { status: AgentStatus; pending: AgentPermission[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const cal = status.calendar;
  const refresh = () => qc.invalidateQueries({ queryKey: ["agent"] });
  const fail = (e: unknown) => toast({ tone: "error", title: e instanceof ApiError ? e.message : "Something went wrong. Try again." });

  const connect = useMutation({
    mutationFn: async () => {
      // Connecting is the explicit grant of "Connect external accounts" for this event.
      if (!status.permissions.includes("integrations")) {
        await api.setAgent(true, Array.from(new Set([...status.permissions, ...pending, "integrations" as const])));
      }
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
  const sync = useMutation({
    mutationFn: () => api.agentAction("sync_agenda_to_calendar", {}),
    onSuccess: (r) => {
      toast({ tone: "success", title: r.reply });
      void refresh();
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

  const canSync = status.permissions.includes("external_actions");
  return (
    <section className="mt-6 rounded-xl border border-line p-3" aria-labelledby="gcal-title">
      <p id="gcal-title" className="flex items-center gap-1.5 text-[13px] font-medium">
        <CalendarSync className="size-4 text-needle" /> Google Calendar
      </p>
      {!cal.configured ? (
        <p className="mt-1 text-[12.5px] text-ink-3">
          Not set up on this server yet. You can still download your agenda as a calendar file from My Agenda.
        </p>
      ) : !cal.connected ? (
        <>
          <p className="mt-1 text-[12.5px] text-ink-3">
            Connect to keep your saved sessions in your calendar. conCompass only gets access to calendar events and your
            list of calendars, and only writes when you sync.
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
          {cal.last_sync && <p className="text-[12px] text-ink-3">{lastSyncText(cal.last_sync)}</p>}
          {!canSync && (
            <p className="text-[12px] text-warn">Allow “Act outside conCompass” above and save to sync.</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="accent" disabled={!canSync || sync.isPending} onClick={() => sync.mutate()}>
              {sync.isPending ? <Loader2 className="animate-spin" /> : <CalendarSync />} Sync my agenda now
            </Button>
            <Button size="sm" variant="danger" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
              <Unlink /> Disconnect
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
