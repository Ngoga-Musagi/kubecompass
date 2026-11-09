"use client";

import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { useParseIntent } from "@/hooks/use-data";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  {
    label: "AI-powered autoscaler",
    text: "I am building an AI-powered Kubernetes autoscaler. I want to understand production AI infrastructure, GPU scheduling, inference optimization, observability, agentic systems, and workload orchestration. I prefer advanced technical talks, demonstrations, and sessions with practical engineering insights.",
  },
  {
    label: "Platform team lead",
    text: "I lead a platform engineering team. I want to learn about internal developer platforms, GitOps, policy as code and multi-tenancy. Intermediate level, practical case studies.",
  },
  {
    label: "New to cloud native",
    text: "I'm new to Kubernetes and cloud native. I want beginner-friendly sessions on getting started, observability basics and security fundamentals. Hands-on tutorials preferred.",
  },
  {
    label: "eBPF & networking",
    text: "I work on networking and want deep dives on eBPF, Cilium, service mesh and Gateway API. Not interested in AI.",
  },
];

export function IntentComposer({
  initial,
  compact = false,
  onParsed,
}: {
  initial?: string | null;
  compact?: boolean;
  onParsed?: () => void;
}) {
  const [text, setText] = React.useState(initial ?? "");
  const parse = useParseIntent();
  const ref = React.useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    if (initial) setText(initial);
  }, [initial]);

  const submit = () => {
    if (text.trim().length < 3) return;
    parse.mutate(text.trim(), { onSuccess: () => onParsed?.() });
  };

  return (
    <div>
      <div
        className={cn(
          "group rounded-2xl border border-line-strong bg-surface shadow-[var(--shadow-md)] transition-[border-color,box-shadow] focus-within:border-ink/40 focus-within:shadow-[0_0_0_4px_var(--ring)]",
        )}
      >
        <label htmlFor="intent" className="sr-only">
          Describe what you want to learn
        </label>
        <textarea
          id="intent"
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
          }}
          rows={compact ? 2 : 3}
          maxLength={2000}
          placeholder="Describe what you're building and what you want to learn. For example: I'm building an AI-powered autoscaler and want to understand GPU scheduling and inference…"
          className="block w-full resize-none rounded-t-2xl bg-transparent px-4 pt-4 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-4"
        />
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 pb-3 pt-1">
          <p className="pl-1 text-[12px] text-ink-4">
            {text.length > 0 ? `${text.length}/2000 · Ctrl+Enter to submit` : "Plain language works best."}
          </p>
          <Button variant="accent" size="md" onClick={submit} disabled={parse.isPending || text.trim().length < 3}>
            {parse.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {parse.isPending ? "Understanding…" : "Plan my conference"}
            {!parse.isPending && <ArrowRight />}
          </Button>
        </div>
      </div>
      {parse.isError && (
        <p role="alert" className="mt-2 text-[12.5px] text-danger">
          {parse.error instanceof ApiError ? parse.error.message : "Couldn't understand that request."}
        </p>
      )}
      {!compact && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[12px] text-ink-3">Try:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              onClick={() => {
                setText(ex.text);
                ref.current?.focus();
              }}
              className="h-7 rounded-full border border-line bg-surface px-3 text-[12px] text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
            >
              {ex.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
