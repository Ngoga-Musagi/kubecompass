"use client";

import {
  Bot,
  CalendarDays,
  Compass,
  Menu,
  Moon,
  Network,
  Sparkles,
  Sun,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { CommandSearch } from "@/components/layout/command-search";
import { IdentityControl } from "@/components/layout/identity-control";
import { Logo } from "@/components/layout/logo";
import { Tooltip } from "@/components/ui/primitives";
import { useConference } from "@/hooks/use-conference";
import { useAgenda } from "@/hooks/use-data";
import { formatDateRange, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Discover", icon: Compass },
  { href: "/recommendations", label: "Recommendations", icon: Sparkles },
  { href: "/graph", label: "Knowledge Graph", icon: Network },
  { href: "/speakers", label: "Speakers", icon: Users },
  { href: "/agenda", label: "My Agenda", icon: CalendarDays },
  { href: "/agent", label: "My Agent", icon: Bot },
];

function useTheme() {
  const [dark, setDark] = React.useState(false);
  React.useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);
  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("kubecompass.theme", next ? "dark" : "light");
    } catch {
      /* ignore */
    }
  };
  return { dark, toggle };
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data: agenda } = useAgenda();
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        const conflicts = href === "/agenda" ? (agenda?.conflicts.length ?? 0) : 0;
        const count = href === "/agenda" ? (agenda?.total ?? 0) : 0;
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group relative flex h-9 items-center gap-2.5 rounded-[10px] px-2.5 text-[13.5px] transition-colors",
              active ? "bg-surface text-ink shadow-[var(--shadow-sm)] ring-1 ring-line" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            <Icon className={cn("size-4", active ? "text-needle" : "text-ink-3 group-hover:text-ink-2")} />
            <span className="flex-1">{label}</span>
            {count > 0 && (
              <span className={cn("rounded-md px-1.5 font-mono text-[10.5px]", conflicts ? "bg-warn-soft text-warn" : "bg-surface-2 text-ink-3")}>
                {count}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

function ConferenceCard() {
  const { conference, conferences, select, isLoading } = useConference();
  if (isLoading) return <div className="skeleton h-[74px]" />;
  if (!conference) return null;
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="eyebrow mb-1">Conference</div>
      {conferences.length > 1 ? (
        <select
          value={conference.id}
          onChange={(e) => select(e.target.value)}
          className="w-full bg-transparent text-[13px] font-medium text-ink outline-none"
          aria-label="Select conference"
        >
          {conferences.map((c) => (
            <option key={c.id} value={c.id}>
              {c.short_name}
            </option>
          ))}
        </select>
      ) : (
        <p className="text-[13px] font-medium leading-snug text-ink">{conference.short_name}</p>
      )}
      <p className="mt-0.5 text-[12px] text-ink-3">
        {conference.city.split(",")[0]} · {formatDateRange(conference.start_date, conference.end_date)}
      </p>
    </div>
  );
}

function Freshness() {
  const { conference } = useConference();
  if (!conference) return null;
  const refreshed = conference.last_refreshed_at;
  return (
    <Tooltip
      content={
        <span>
          Official {conference.source_system} data · version {conference.data_version}
          <br />
          {conference.session_count} sessions · {conference.speaker_count} speakers
        </span>
      }
    >
      <div className="flex items-center gap-2 px-1 text-[12px] text-ink-3">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-ok/40" />
          <span className="relative inline-flex size-2 rounded-full bg-ok" />
        </span>
        Data refreshed {relativeTime(refreshed)}
      </div>
    </Tooltip>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const { dark, toggle } = useTheme();
  const pathname = usePathname();
  React.useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const sidebar = (
    <div className="flex h-full flex-col gap-5 px-3 py-4">
      <Link href="/" className="px-1.5" aria-label="conCompass home">
        <Logo />
      </Link>
      <ConferenceCard />
      <NavLinks onNavigate={() => setMobileOpen(false)} />
      <div className="mt-auto flex flex-col gap-3">
        <Freshness />
        <IdentityControl onDone={() => setMobileOpen(false)} />
        <button
          onClick={toggle}
          className="flex h-8 items-center gap-2 rounded-lg px-2 text-[12.5px] text-ink-3 hover:bg-surface-2 hover:text-ink"
        >
          {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          {dark ? "Light theme" : "Dark theme"}
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] border-r border-line bg-bg lg:block">{sidebar}</aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-[280px] animate-rise border-r border-line bg-bg">
            <button className="absolute right-3 top-4 rounded-md p-1 text-ink-3" onClick={() => setMobileOpen(false)} aria-label="Close menu">
              <X className="size-4" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}
      <div className="lg:pl-[248px]">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur-md sm:px-6">
          <button className="rounded-md p-1.5 text-ink-2 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <Link href="/" className="lg:hidden" aria-label="conCompass home">
            <Logo className="[&_span:last-child]:hidden sm:[&_span:last-child]:inline" />
          </Link>
          <div className="flex min-w-0 flex-1 justify-end lg:justify-start">
            <CommandSearch />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1320px] px-4 pb-24 pt-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
