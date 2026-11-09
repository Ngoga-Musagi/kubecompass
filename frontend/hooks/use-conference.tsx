"use client";

import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { api, setApiConference } from "@/lib/api";
import type { ConferenceInfo } from "@/types/api";

interface ConferenceState {
  conferences: ConferenceInfo[];
  conference: ConferenceInfo | null;
  timeZone: string;
  select: (id: string) => void;
  isLoading: boolean;
  error: unknown;
  refetch: () => void;
}

const Ctx = React.createContext<ConferenceState | null>(null);
const KEY = "kubecompass.conference";

export function ConferenceProvider({ children }: { children: React.ReactNode }) {
  const q = useQuery({ queryKey: ["conferences"], queryFn: api.conferences, staleTime: 5 * 60_000 });
  const [selected, setSelected] = React.useState<string | null>(null);

  React.useEffect(() => {
    try {
      setSelected(window.localStorage.getItem(KEY));
    } catch {
      /* storage unavailable */
    }
  }, []);

  const conference = React.useMemo(() => {
    const list = q.data ?? [];
    return list.find((c) => c.id === selected) ?? list[0] ?? null;
  }, [q.data, selected]);

  // Synchronously scope API calls before children issue queries.
  setApiConference(conference?.id ?? null);

  const select = React.useCallback((id: string) => {
    setSelected(id);
    try {
      window.localStorage.setItem(KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const value: ConferenceState = {
    conferences: q.data ?? [],
    conference,
    timeZone: conference?.timezone ?? "UTC",
    select,
    isLoading: q.isLoading,
    error: q.error,
    refetch: () => void q.refetch(),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useConference(): ConferenceState {
  const v = React.useContext(Ctx);
  if (!v) throw new Error("useConference must be used inside ConferenceProvider");
  return v;
}
