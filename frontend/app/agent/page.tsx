"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Bot, Loader2, Mic, Settings2, Square, Volume2, VolumeX, Wrench } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { AgentCards } from "@/components/agent/agent-cards";
import { AnswerText } from "@/components/assistant/answer-text";
import { AgentSetup, PermissionChooser } from "@/components/agent/agent-permissions";
import { CalendarSection } from "@/components/agent/calendar-section";
import { Button } from "@/components/ui/button";
import { Badge, ErrorState, Skeleton } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { useConference } from "@/hooks/use-conference";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LOW_CONFIDENCE, speakable, speechInput, speechOutput } from "@/lib/voice";
import type { AgentPermission, AgentReply, AgentStatus } from "@/types/api";

interface Turn {
  role: "user" | "assistant";
  content: string;
  voice?: boolean;
  reply?: AgentReply;
}

const TOOL_LABELS: Record<string, string> = {
  search_sessions: "Searched sessions",
  search_speakers: "Searched speakers",
  get_session_details: "Looked up the session",
  recommend_sessions: "Ranked sessions for your goals",
  sessions_in_free_time: "Checked what starts soon",
  get_user_agenda: "Read your agenda",
  next_session: "Found your next session",
  check_schedule_conflicts: "Checked your agenda for conflicts",
  suggest_agenda: "Planned around your agenda",
  grounded_answer: "Answered from the event data",
  sync_agenda_to_calendar: "Synced your Google Calendar",
};

/** A day inside the event to plan: tomorrow while the event runs, otherwise its first day. */
function planDay(start: string | null, end: string | null): string {
  if (!start || !end) return "Wednesday";
  const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
  const day = tomorrow >= start && tomorrow <= end ? tomorrow : start;
  return new Date(`${day}T12:00:00`).toLocaleDateString("en-US", { weekday: "long" });
}

function suggestions(start: string | null, end: string | null): string[] {
  return [
    "What session should I attend next?",
    "I have 30 minutes free. What would you recommend?",
    `Build my agenda for ${planDay(start, end)}`,
    "Find something related to GPU scheduling",
    "Do I have any conflicts?",
    "Who is speaking about platform engineering?",
  ];
}

function useAgentStatus() {
  const { conference } = useConference();
  return useQuery({ queryKey: ["agent", conference?.id ?? "default"], queryFn: api.agent, enabled: !!conference });
}

function AgentSettings({ status, open, onOpenChange }: { status: AgentStatus; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [perms, setPerms] = React.useState<AgentPermission[]>(status.permissions);
  React.useEffect(() => {
    setPerms(status.permissions);
  }, [status.permissions]);
  const refresh = (s: AgentStatus) => {
    qc.setQueryData(["agent", s.conference_id], s);
    void qc.invalidateQueries({ queryKey: ["profile"] });
    void qc.invalidateQueries({ queryKey: ["recommendations"] });
  };
  const save = useMutation({
    mutationFn: () => api.setAgent(true, perms),
    onSuccess: (s) => {
      refresh(s);
      toast({ tone: "success", title: "Permissions updated" });
    },
  });
  const clear = useMutation({
    mutationFn: api.clearAgentMemory,
    onSuccess: (s) => {
      refresh(s);
      toast({ tone: "success", title: "Your interests and goals were cleared" });
    },
  });
  const off = useMutation({
    mutationFn: () => api.setAgent(false),
    onSuccess: (s) => {
      refresh(s);
      onOpenChange(false);
      toast({ tone: "info", title: "Agent turned off", description: "All permissions were revoked." });
    },
  });
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Agent permissions"
      description="What your agent may do within this event. Changes apply immediately."
      footer={
        <div className="flex flex-wrap justify-between gap-2">
          <Button variant="danger" size="sm" onClick={() => off.mutate()} disabled={off.isPending}>
            Turn off agent
          </Button>
          <Button variant="accent" size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
            Save permissions
          </Button>
        </div>
      }
    >
      <PermissionChooser status={status} value={perms} onChange={setPerms} />
      <CalendarSection status={status} pending={perms} />
      <div className="mt-6 rounded-xl border border-line p-3">
        <p className="text-[13px] font-medium">What it knows about you</p>
        <p className="mt-0.5 text-[12.5px] text-ink-3">
          {status.has_profile ? "Your interests and goals for this event." : "Nothing yet: tell it your goals here or on Discover."}
        </p>
        <div className="mt-2.5 flex flex-wrap gap-2">
          <Link href="/" className="text-[12.5px] font-medium text-needle-ink hover:underline">
            View or edit on Discover
          </Link>
          {status.has_profile && (
            <button className="text-[12.5px] font-medium text-danger hover:underline" onClick={() => clear.mutate()}>
              Clear interests and goals
            </button>
          )}
        </div>
      </div>
      {status.audit.length > 0 && (
        <div className="mt-6">
          <p className="eyebrow mb-2">Recent actions you confirmed</p>
          <ul className="space-y-1.5 text-[12.5px] text-ink-2">
            {status.audit.slice(0, 8).map((a, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span className="truncate">
                  {a.tool === "add_session_to_agenda"
                    ? "Added a session"
                    : a.tool === "sync_agenda_to_calendar"
                      ? "Synced to Google Calendar"
                      : "Removed a session"}
                  {a.outcome === "failed" && " (failed)"}
                </span>
                <span className="shrink-0 text-ink-4">{new Date(a.at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Sheet>
  );
}

function modelLabel(servedBy: string): string {
  const [provider, ...rest] = servedBy.split(":");
  const model = rest.join(":").replace(/-q\d.*$/i, "");
  return provider === "ollama" ? `${model} (local)` : model;
}

function AgentTurn({ r, onSpeak }: { r: AgentReply; onSpeak: (text: string) => void }) {
  const [showTrace, setShowTrace] = React.useState(false);
  const tools = r.trace.filter((t) => t.status === "ok");
  return (
    <div className="flex gap-3">
      <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-ink text-bg">
        <Bot className="size-4" />
      </span>
      <div className="min-w-0 flex-1 space-y-3">
        {r.citations.length > 0 ? (
          <AnswerText text={r.reply} citations={r.citations} />
        ) : (
          <p className="text-[14.5px] leading-relaxed text-ink">{speakable(r.reply)}</p>
        )}
        <AgentCards cards={r.cards} />
        <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
          {r.mode === "llm" && r.generated_by && <Badge tone="needle">AI wording · {modelLabel(r.generated_by)}</Badge>}
          {r.mode === "retrieval_only" && <Badge tone="neutral">From the official schedule</Badge>}
          {speechOutput.supported && (
            <button onClick={() => onSpeak(r.reply)} className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-surface-2 hover:text-ink" aria-label="Read this reply aloud">
              <Volume2 className="size-3.5" /> Listen
            </button>
          )}
          {tools.length > 0 && (
            <button onClick={() => setShowTrace((v) => !v)} className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-surface-2 hover:text-ink" aria-expanded={showTrace}>
              <Wrench className="size-3.5" /> How I got this
            </button>
          )}
        </div>
        {showTrace && (
          <ul className="space-y-0.5 text-[12px] text-ink-3">
            {r.trace.map((t, i) => (
              <li key={i}>
                {t.status === "denied" ? "Not allowed: " : "✓ "}
                {TOOL_LABELS[t.tool] ?? t.tool}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function AgentPage() {
  const { conference } = useConference();
  const qc = useQueryClient();
  const status = useAgentStatus();
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [draft, setDraft] = React.useState("");
  const [listening, setListening] = React.useState(false);
  const [partial, setPartial] = React.useState("");
  const [voiceError, setVoiceError] = React.useState<string | null>(null);
  const [speaking, setSpeaking] = React.useState(false);
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [micSupported, setMicSupported] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    setMicSupported(speechInput.supported);
    return () => speechOutput.cancel();
  }, []);

  const toast = useToast();
  // Back from Google's consent screen: say what happened and reopen the permissions panel.
  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("calendar");
    if (!result) return;
    window.history.replaceState(null, "", window.location.pathname);
    if (result === "connected") toast({ tone: "success", title: "Google Calendar connected", description: "Allow “Act outside conCompass”, then sync." });
    else if (result === "cancelled") toast({ tone: "info", title: "Google Calendar wasn't connected" });
    else toast({ tone: "error", title: "Couldn't connect Google Calendar", description: params.get("reason") ?? undefined });
    void qc.invalidateQueries({ queryKey: ["agent"] });
    setSettingsOpen(true);
  }, [qc, toast]);

  const enable = useMutation({
    mutationFn: (perms: AgentPermission[]) => api.setAgent(true, perms),
    onSuccess: (s) => qc.setQueryData(["agent", s.conference_id], s),
  });

  const speak = React.useCallback((text: string) => {
    setSpeaking(true);
    speechOutput.speak(text, () => setSpeaking(false));
  }, []);

  const chat = useMutation({
    mutationFn: ({ message }: { message: string; voice: boolean }) =>
      api.agentChat(
        message,
        turns.map((t) => ({ role: t.role, content: t.content })).slice(-6),
      ),
    onSuccess: (r, vars) => {
      setTurns((t) => [...t, { role: "assistant", content: r.reply, reply: r }]);
      if (vars.voice) speak(r.reply); // answered by voice → reply by voice
      if (r.needs_permission) void status.refetch();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "agent_disabled") void status.refetch();
    },
  });

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, chat.isPending]);

  const send = (text: string, voice = false) => {
    const m = text.trim();
    if (!m || chat.isPending) return;
    setTurns((t) => [...t, { role: "user", content: m, voice }]);
    setDraft("");
    chat.mutate({ message: m, voice });
  };

  const toggleMic = () => {
    setVoiceError(null);
    if (listening) {
      speechInput.stop();
      return;
    }
    speechOutput.cancel();
    setSpeaking(false);
    setListening(true);
    setPartial("");
    speechInput.start({
      onPartial: setPartial,
      onFinal: (text, confidence) => {
        setPartial("");
        if (!text) return;
        // Noisy room: let the attendee check a low-confidence transcript before sending.
        if (confidence !== null && confidence < LOW_CONFIDENCE) {
          setDraft(text);
          setVoiceError("I may have misheard. Check the text, then send.");
        } else {
          send(text, true);
        }
      },
      onError: setVoiceError,
      onEnd: () => setListening(false),
    });
  };

  if (status.isLoading || !conference) {
    return (
      <div className="mx-auto max-w-3xl space-y-3 py-8">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-24" />
      </div>
    );
  }
  if (status.isError) return <ErrorState error={status.error} onRetry={() => void status.refetch()} className="mx-auto mt-10 max-w-xl" />;
  const st = status.data!;
  if (!st.enabled) {
    return <AgentSetup status={st} eventName={conference.short_name} busy={enable.isPending} onEnable={(p) => enable.mutate(p)} />;
  }

  const chips = suggestions(conference.start_date, conference.end_date);
  return (
    <div className="mx-auto flex min-h-[calc(100dvh-140px)] max-w-3xl flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-line pb-3">
        <div className="min-w-0">
          <p className="eyebrow flex items-center gap-1.5">
            <Bot className="size-3 text-needle" /> Your event agent · {conference.short_name}
          </p>
          <p className="mt-1 truncate text-[12.5px] text-ink-3">
            Allowed: {st.permissions.map((p) => st.catalog.find((c) => c.id === p)?.title.toLowerCase()).join(", ")}
            {!st.has_profile && " · tell me your goals to personalize"}
          </p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => setSettingsOpen(true)} aria-label="Agent permissions and memory">
          <Settings2 /> <span className="hidden sm:inline">Permissions</span>
        </Button>
      </div>

      {turns.length === 0 ? (
        <div className="flex flex-1 flex-col justify-center py-8">
          <h1 className="font-display text-[32px] leading-tight sm:text-[38px]">How can I help at {conference.short_name}?</h1>
          <p className="mt-2 max-w-xl text-[14.5px] text-ink-2">
            Ask by voice or text. I use only this event&apos;s official schedule and ask before changing your agenda.
          </p>
          <div className="mt-6 grid gap-2 sm:grid-cols-2">
            {chips.map((s) => (
              <button key={s} onClick={() => send(s)} className="card min-h-11 px-3.5 py-3 text-left text-[13.5px] text-ink-2 transition-colors hover:border-line-strong hover:text-ink">
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 space-y-7 py-5" aria-live="polite">
          {turns.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[14px] text-bg">
                  {t.voice && <Mic className="mr-1.5 inline size-3.5 opacity-70" aria-label="Spoken" />}
                  {t.content}
                </p>
              </div>
            ) : (
              <AgentTurn key={i} r={t.reply!} onSpeak={speak} />
            ),
          )}
          {chat.isPending && (
            <div className="flex items-center gap-2 text-[13px] text-ink-3">
              <Loader2 className="size-4 animate-spin" /> Working on it…
            </div>
          )}
          {chat.isError && <ErrorState error={chat.error} />}
          <div ref={endRef} />
        </div>
      )}

      <div className="sticky bottom-4 mt-4 space-y-2">
        {(voiceError || listening || speaking) && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-3 py-2 text-[12.5px] shadow-[var(--shadow-sm)]" role="status">
            <span className={cn("min-w-0 truncate", voiceError ? "text-warn" : "text-ink-2")}>
              {voiceError ?? (listening ? partial || "Listening… speak now" : "Speaking…")}
            </span>
            {speaking && (
              <button
                onClick={() => {
                  speechOutput.cancel();
                  setSpeaking(false);
                }}
                className="inline-flex shrink-0 items-center gap-1 font-medium text-ink-2 hover:text-ink"
              >
                <VolumeX className="size-3.5" /> Stop
              </button>
            )}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
        >
          <div className="flex items-end gap-2 rounded-2xl border border-line-strong bg-surface p-2 shadow-[var(--shadow-lg)] focus-within:shadow-[0_0_0_4px_var(--ring)]">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(draft);
                }
              }}
              rows={1}
              maxLength={1000}
              placeholder={listening ? "Listening…" : "Ask your agent…"}
              className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] outline-none placeholder:text-ink-4"
              aria-label="Message your agent"
            />
            {micSupported && (
              <button
                type="button"
                onClick={toggleMic}
                className={cn(
                  "relative flex size-11 shrink-0 items-center justify-center rounded-xl border transition-colors",
                  listening ? "border-needle bg-needle text-white" : "border-line text-ink-2 hover:bg-surface-2 hover:text-ink",
                )}
                aria-label={listening ? "Stop listening" : "Speak to your agent"}
                aria-pressed={listening}
              >
                {listening && <span className="absolute inset-0 animate-ping rounded-xl bg-needle/30" aria-hidden />}
                {listening ? <Square className="size-4" /> : <Mic className="size-5" />}
              </button>
            )}
            <button
              type="submit"
              disabled={!draft.trim() || chat.isPending}
              className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-needle text-white transition-opacity disabled:opacity-40"
              aria-label="Send"
            >
              <ArrowUp className="size-5" />
            </button>
          </div>
        </form>
        {!micSupported && <p className="px-1 text-[11.5px] text-ink-4">Voice input isn&apos;t available in this browser; typing works everywhere.</p>}
      </div>
      <AgentSettings status={st} open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
