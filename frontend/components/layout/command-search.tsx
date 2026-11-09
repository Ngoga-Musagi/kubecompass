"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, CornerDownLeft, Hash, Search, User } from "lucide-react";
import { Dialog } from "radix-ui";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Kbd } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { entityHref, sessionHref, speakerHref } from "@/lib/format";
import { cn, entityColor, ENTITY_LABEL } from "@/lib/utils";

interface Item {
  key: string;
  href: string;
  label: string;
  hint: string;
  icon: React.ReactNode;
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** ⌘K palette: autocomplete (ES search_as_you_type) across sessions, speakers and concepts. */
export function CommandSearch() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [active, setActive] = React.useState(0);
  const dq = useDebounced(q.trim(), 140);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const { data, isFetching } = useQuery({
    queryKey: ["suggest", dq],
    queryFn: () => api.suggest(dq),
    enabled: open && dq.length >= 2,
    staleTime: 30_000,
  });

  const items: Item[] = React.useMemo(() => {
    const out: Item[] = [];
    if (dq.length >= 2) {
      out.push({
        key: "search",
        href: `/search?q=${encodeURIComponent(dq)}`,
        label: `Search sessions for “${dq}”`,
        hint: "Hybrid search",
        icon: <Search className="size-4 text-ink-3" />,
      });
    }
    data?.entities.forEach((e) =>
      out.push({
        key: e.id,
        href: entityHref(e.id),
        label: e.name,
        hint: `${ENTITY_LABEL[e.type] ?? e.type} · ${e.session_count} sessions`,
        icon: <Hash className="size-4" style={{ color: entityColor(e.type) }} />,
      }),
    );
    data?.sessions.forEach((s) =>
      out.push({
        key: s.id,
        href: sessionHref(s.id),
        label: s.title,
        hint: s.track ?? "Session",
        icon: <CalendarClock className="size-4 text-ink-3" />,
      }),
    );
    data?.speakers.forEach((p) =>
      out.push({
        key: p.id,
        href: speakerHref(p.id),
        label: p.full_name,
        hint: p.company ?? "Speaker",
        icon: <User className="size-4" style={{ color: "var(--ent-speaker)" }} />,
      }),
    );
    return out;
  }, [data, dq]);

  React.useEffect(() => setActive(0), [dq]);

  const go = (item?: Item) => {
    if (!item) return;
    setOpen(false);
    setQ("");
    router.push(item.href);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="group flex h-9 w-full min-w-0 max-w-[420px] items-center gap-2 rounded-[10px] border border-line bg-surface px-3 text-left text-[13px] text-ink-3 transition-colors hover:border-line-strong"
      >
        <Search className="size-4" />
        <span className="min-w-0 flex-1 truncate"><span className="sm:hidden">Search</span><span className="hidden sm:inline">Search sessions, speakers, technologies…</span></span>
        <span className="hidden items-center gap-0.5 sm:flex">
          <Kbd>Ctrl</Kbd>
          <Kbd>K</Kbd>
        </span>
      </button>
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 animate-fade bg-black/25 backdrop-blur-[2px]" />
          <Dialog.Content className="fixed left-1/2 top-[12vh] z-50 w-[min(94vw,620px)] -translate-x-1/2 animate-rise overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-lg)]">
            <Dialog.Title className="sr-only">Search KubeCompass</Dialog.Title>
            <Dialog.Description className="sr-only">Find sessions, speakers, topics and technologies</Dialog.Description>
            <div className="flex items-center gap-2 border-b border-line px-4">
              <Search className="size-4 text-ink-3" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setActive((a) => Math.min(a + 1, items.length - 1));
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setActive((a) => Math.max(a - 1, 0));
                  } else if (e.key === "Enter") {
                    e.preventDefault();
                    go(items[active]);
                  }
                }}
                placeholder="Try “GPU sharing”, “eBPF”, a speaker or a project…"
                className="h-12 flex-1 bg-transparent text-[14px] text-ink outline-none placeholder:text-ink-4"
                aria-label="Search"
              />
              {isFetching && <span className="size-3 animate-spin rounded-full border-2 border-line border-t-needle" />}
            </div>
            <ul className="scrollbar-thin max-h-[52vh] overflow-y-auto p-1.5" role="listbox">
              {items.length === 0 && (
                <li className="px-3 py-8 text-center text-[13px] text-ink-3">
                  {dq.length < 2 ? "Type at least two characters." : isFetching ? "Searching…" : "No matches in the conference data."}
                </li>
              )}
              {items.map((it, i) => (
                <li key={it.key} role="option" aria-selected={i === active}>
                  <button
                    onMouseEnter={() => setActive(i)}
                    onClick={() => go(it)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left",
                      i === active ? "bg-surface-2" : "hover:bg-surface-2",
                    )}
                  >
                    {it.icon}
                    <span className="min-w-0 flex-1 truncate text-[13.5px] text-ink">{it.label}</span>
                    <span className="hidden shrink-0 truncate text-[12px] text-ink-3 sm:block sm:max-w-[180px]">{it.hint}</span>
                    {i === active && <CornerDownLeft className="size-3.5 shrink-0 text-ink-4" />}
                  </button>
                </li>
              ))}
            </ul>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
