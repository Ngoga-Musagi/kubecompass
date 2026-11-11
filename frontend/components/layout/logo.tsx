import { cn } from "@/lib/utils";

/** conCompass mark: a compass rose whose needle points north-east (toward discovery). */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <circle cx="16" cy="16" r="14.5" fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="10" fill="none" stroke="var(--border-strong)" strokeWidth="1" strokeDasharray="1.5 2.6" />
      <path d="M16 16 L23.5 8.5 L18.2 17.4 Z" fill="var(--needle)" />
      <path d="M16 16 L8.5 23.5 L13.8 14.6 Z" fill="var(--ink)" />
      <circle cx="16" cy="16" r="1.6" fill="var(--surface)" stroke="var(--ink)" strokeWidth="1" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <LogoMark />
      <span className="font-display text-[21px] leading-none tracking-tight text-ink">
        con<span className="italic text-needle-ink">Compass</span>
      </span>
    </span>
  );
}
