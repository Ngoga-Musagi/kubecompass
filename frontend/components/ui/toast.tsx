"use client";

import { CheckCircle2, Info, TriangleAlert } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

type Tone = "success" | "info" | "error";
interface ToastItem {
  id: number;
  tone: Tone;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

const ToastContext = React.createContext<(t: Omit<ToastItem, "id">) => void>(() => {});

export function useToast() {
  return React.useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const push = React.useCallback((t: Omit<ToastItem, "id">) => {
    const id = Date.now() + Math.random();
    setItems((cur) => [...cur.slice(-2), { ...t, id }]);
    setTimeout(() => setItems((cur) => cur.filter((x) => x.id !== id)), 4200);
  }, []);
  const Icon = { success: CheckCircle2, info: Info, error: TriangleAlert };
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 left-1/2 z-[60] flex w-[min(92vw,380px)] -translate-x-1/2 flex-col gap-2 sm:left-auto sm:right-4 sm:translate-x-0">
        {items.map((t) => {
          const I = Icon[t.tone];
          return (
            <div key={t.id} className="pointer-events-auto flex animate-rise items-start gap-2.5 rounded-xl border border-line bg-surface p-3 shadow-[var(--shadow-lg)]">
              <I className={cn("mt-0.5 size-4 shrink-0", t.tone === "success" && "text-ok", t.tone === "info" && "text-high", t.tone === "error" && "text-danger")} />
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-ink">{t.title}</p>
                {t.description && <p className="mt-0.5 text-[12.5px] text-ink-3">{t.description}</p>}
              </div>
              {t.action && (
                <button onClick={t.action.onClick} className="shrink-0 text-[12.5px] font-medium text-needle-ink hover:underline">
                  {t.action.label}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
