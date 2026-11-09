"use client";

import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { Tooltip as TooltipPrimitive } from "radix-ui";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

/* ---------- Badge ------------------------------------------------------------------------ */
export function Badge({
  className,
  tone = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & {
  tone?: "neutral" | "must" | "high" | "explore" | "warn" | "danger" | "needle" | "outline";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-surface-2 text-ink-2",
    outline: "border border-line text-ink-2",
    must: "bg-must-soft text-must",
    high: "bg-high-soft text-high",
    explore: "bg-explore-soft text-explore",
    warn: "bg-warn-soft text-warn",
    danger: "bg-danger-soft text-danger",
    needle: "bg-needle-soft text-needle-ink",
  };
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-1 rounded-md px-1.5 text-[11.5px] font-medium [&_svg]:size-3",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}

/* ---------- Tooltip ---------------------------------------------------------------------- */
export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <TooltipPrimitive.Root delayDuration={200}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-[300px] animate-fade rounded-lg bg-ink px-2.5 py-1.5 text-[12px] leading-snug text-bg shadow-[var(--shadow-lg)]"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

/* ---------- Skeleton --------------------------------------------------------------------- */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton", className)} />;
}

/* ---------- Avatar ----------------------------------------------------------------------- */
export function Avatar({ name, src, size = 32 }: { name: string; src?: string | null; size?: number }) {
  const [failed, setFailed] = React.useState(false);
  const style = { width: size, height: size };
  if (src && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- remote Sessionize CDN, sized by CSS
      <img
        src={src}
        alt=""
        style={style}
        onError={() => setFailed(true)}
        className="shrink-0 rounded-full border border-line object-cover"
        loading="lazy"
      />
    );
  }
  return (
    <span
      style={{ ...style, fontSize: Math.max(10, size * 0.36) }}
      className="inline-flex shrink-0 items-center justify-center rounded-full border border-line bg-surface-2 font-medium text-ink-2"
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}

/* ---------- States ----------------------------------------------------------------------- */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-[14px] border border-dashed border-line-strong px-6 py-12 text-center", className)}>
      <div className="mb-3 flex size-10 items-center justify-center rounded-full bg-surface-2 text-ink-3">
        <Icon className="size-5" />
      </div>
      <p className="text-[14px] font-medium text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-[13px] text-ink-3">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className={cn("flex items-start gap-3 rounded-[14px] border border-danger/25 bg-danger-soft/60 p-4", className)}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-ink">Couldn&apos;t load this</p>
        <p className="mt-0.5 text-[13px] text-ink-2">{message}</p>
      </div>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          <RefreshCw /> Retry
        </Button>
      )}
    </div>
  );
}

/* ---------- Section header --------------------------------------------------------------- */
export function SectionHeader({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-4 flex flex-wrap items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
        <h2 className="text-[17px] font-semibold tracking-tight text-ink">{title}</h2>
        {description && <p className="mt-1 text-[13px] text-ink-3">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/* ---------- Segmented control ------------------------------------------------------------ */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; hint?: string }[];
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-[10px] border border-line bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          title={o.hint}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-7 rounded-[8px] px-2.5 text-[12.5px] font-medium text-ink-3 transition-colors",
            value === o.value ? "bg-surface text-ink shadow-[var(--shadow-sm)]" : "hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-line bg-surface px-1 font-mono text-[10.5px] text-ink-3">
      {children}
    </kbd>
  );
}
