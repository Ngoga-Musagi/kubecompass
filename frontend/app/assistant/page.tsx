"use client";

import { useMutation } from "@tanstack/react-query";
import { ArrowUp, Bot, Database, Loader2, MessagesSquare } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { AnswerText } from "@/components/assistant/answer-text";
import { EntityChip, OriginBadge, SessionMeta } from "@/components/sessions/session-parts";
import { Avatar, Badge, ErrorState } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { api } from "@/lib/api";
import { sessionHref, speakerHref } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ChatResponse } from "@/types/api";

const SUGGESTIONS = [
  "Which sessions discuss production AI infrastructure?",
  "Who is speaking about Kubernetes scheduling?",
  "Are there sessions about eBPF and networking?",
  "Which talks cover GPU scheduling and inference?",
  "Which speakers are working on agentic AI?",
  "What am I missing from my agenda?",
];

/** "ollama:qwen3.5:4b-q4_K_M" -> "qwen3.5:4b (local)"; "anthropic:claude-…" -> "claude-…" */
function modelLabel(servedBy: string): string {
  const [provider, ...rest] = servedBy.split(":");
  const model = rest.join(":").replace(/-q\d.*$/i, "");
  return provider === "ollama" ? `${model} (local)` : model;
}

interface Turn {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
}

function AssistantTurn({ r }: { r: ChatResponse }) {
  return (
    <div className="flex gap-3">
      <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-ink text-bg">
        <Bot className="size-4" />
      </span>
      <div className="min-w-0 flex-1 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {r.mode === "llm" && (
            <Badge tone="needle">
              AI answer · grounded in {r.citations.length} records
              {r.generated_by && ` · ${modelLabel(r.generated_by)}`}
            </Badge>
          )}
          {r.mode === "retrieval_only" && (
            <Badge tone="neutral">
              <Database /> Retrieved from the official schedule
            </Badge>
          )}
          {r.mode === "no_results" && <Badge tone="warn">Not found in the conference data</Badge>}
        </div>
        <AnswerText text={r.answer} citations={r.citations} />
        {r.speakers.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2">
            {r.speakers.map((s, i) => (
              <Link key={s.id} href={speakerHref(s.id)} className="card flex items-center gap-2.5 p-2.5 hover:border-line-strong">
                <span className="font-mono text-[10.5px] text-ink-4">P{i + 1}</span>
                <Avatar name={s.full_name} src={s.photo_url} size={30} />
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium">{s.full_name}</span>
                  <span className="block truncate text-[11.5px] text-ink-3">{s.company}</span>
                </span>
              </Link>
            ))}
          </div>
        )}
        {r.sessions.length > 0 && (
          <ul className="card divide-y divide-line overflow-hidden">
            {r.sessions.map((s, i) => (
              <li key={s.id} className="flex gap-3 px-3.5 py-3">
                <span className="pt-0.5 font-mono text-[10.5px] text-ink-4">S{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <Link href={sessionHref(s.id)} className="text-[13.5px] font-medium leading-snug hover:underline">
                    {s.title}
                  </Link>
                  <SessionMeta session={s} className="mt-1" />
                </div>
              </li>
            ))}
          </ul>
        )}
        {r.concepts.length > 0 && (
          <div>
            <p className="eyebrow mb-2">Connected concepts</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {r.concepts.slice(0, 8).map((c) => (
                <span key={`${c.id}-${c.relation}`} className="inline-flex items-center gap-1">
                  <EntityChip entity={{ id: c.id, name: c.name, type: c.type as never, origin: c.origin, evidence: c.evidence }} />
                  {c.origin === "inferred" && <OriginBadge origin="inferred" />}
                </span>
              ))}
            </div>
          </div>
        )}
        {r.notice && r.mode !== "no_results" && <p className="text-[12px] text-ink-3">{r.notice}</p>}
      </div>
    </div>
  );
}

export default function AssistantPage() {
  const { conference } = useConference();
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [draft, setDraft] = React.useState("");
  const endRef = React.useRef<HTMLDivElement>(null);
  const chat = useMutation({
    mutationFn: (message: string) =>
      api.chat(
        message,
        turns.map((t) => ({ role: t.role, content: t.content })).slice(-6),
      ),
    onSuccess: (r) => setTurns((t) => [...t, { role: "assistant", content: r.answer, response: r }]),
  });

  React.useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [turns, chat.isPending]);

  const send = (text: string) => {
    const m = text.trim();
    if (!m || chat.isPending) return;
    setTurns((t) => [...t, { role: "user", content: m }]);
    setDraft("");
    chat.mutate(m);
  };

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-140px)] max-w-3xl flex-col">
      {turns.length === 0 ? (
        <div className="flex flex-1 flex-col justify-center py-8">
          <div className="eyebrow mb-3 flex items-center gap-1.5">
            <MessagesSquare className="size-3" /> Conference assistant
          </div>
          <h1 className="font-display text-[40px] leading-tight">Ask anything about {conference?.short_name ?? "the conference"}</h1>
          <p className="mt-2 max-w-xl text-[14.5px] text-ink-2">
            Answers come from the indexed schedule, speakers and knowledge graph, with links to every source. If the data doesn&apos;t cover it, the assistant says so.
          </p>
          <div className="mt-6 grid gap-2 sm:grid-cols-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} className="card px-3.5 py-3 text-left text-[13.5px] text-ink-2 transition-colors hover:border-line-strong hover:text-ink">
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 space-y-8 py-4" aria-live="polite">
          {turns.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[14px] text-bg">{t.content}</p>
              </div>
            ) : (
              <AssistantTurn key={i} r={t.response!} />
            ),
          )}
          {chat.isPending && (
            <div className="flex items-center gap-2 text-[13px] text-ink-3">
              <Loader2 className="size-4 animate-spin" /> Searching the conference data…
            </div>
          )}
          {chat.isError && <ErrorState error={chat.error} onRetry={() => turns.at(-1) && chat.mutate(turns.at(-1)!.content)} />}
          <div ref={endRef} />
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
        className="sticky bottom-4 mt-4"
      >
        <div className={cn("flex items-end gap-2 rounded-2xl border border-line-strong bg-surface p-2 shadow-[var(--shadow-lg)] focus-within:shadow-[0_0_0_4px_var(--ring)]")}>
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
            placeholder="Ask about sessions, speakers, technologies…"
            className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[14.5px] outline-none placeholder:text-ink-4"
            aria-label="Message"
          />
          <button type="submit" disabled={!draft.trim() || chat.isPending} className="flex size-10 items-center justify-center rounded-xl bg-needle text-white transition-opacity disabled:opacity-40" aria-label="Send">
            <ArrowUp className="size-5" />
          </button>
        </div>
      </form>
    </div>
  );
}
