"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { useToast } from "@/components/ui/toast";
import { useConference } from "@/hooks/use-conference";
import { api, ApiError } from "@/lib/api";
import type { AgendaView, InterestProfile, SessionFilters } from "@/types/api";

/** Query keys always include the conference so switching conferences never mixes data. */
export function useKeys() {
  const { conference } = useConference();
  const cid = conference?.id ?? "default";
  return useMemo(
    () => ({
      profile: ["profile", cid] as const,
      recs: (f?: SessionFilters) => ["recommendations", cid, f ?? {}] as const,
      agenda: ["agenda", cid] as const,
      pathways: ["pathways", cid] as const,
    }),
    [cid],
  );
}

export function useProfile() {
  const keys = useKeys();
  const { conference } = useConference();
  return useQuery({ queryKey: keys.profile, queryFn: api.profile, enabled: !!conference });
}

export function useRecommendations(filters?: SessionFilters, enabled = true) {
  const keys = useKeys();
  const { conference } = useConference();
  return useQuery({
    queryKey: keys.recs(filters),
    queryFn: () => api.recommendations(filters),
    enabled: !!conference && enabled,
    staleTime: 60_000,
  });
}

export function useAgenda() {
  const keys = useKeys();
  const { conference } = useConference();
  return useQuery({ queryKey: keys.agenda, queryFn: api.agenda, enabled: !!conference });
}

export function useAgendaIds(): Set<string> {
  const { data } = useAgenda();
  return useMemo(() => {
    const ids = new Set<string>();
    data?.days.forEach((d) => d.entries.forEach((e) => ids.add(e.session.id)));
    data?.unscheduled.forEach((e) => ids.add(e.session.id));
    return ids;
  }, [data]);
}

export function useAgendaMutations() {
  const qc = useQueryClient();
  const keys = useKeys();
  const toast = useToast();
  const onDone = (view: AgendaView) => {
    qc.setQueryData(keys.agenda, view);
    // Recommendations carry agenda feasibility annotations; refresh them in the background.
    qc.invalidateQueries({ queryKey: ["recommendations"] });
  };
  const add = useMutation({
    mutationFn: (id: string) => api.addToAgenda(id),
    onSuccess: (view, id) => {
      onDone(view);
      const conflict = view.conflicts.find((c) => c.session_ids.includes(id));
      toast(
        conflict
          ? { tone: "info", title: "Added, with a time conflict", description: `Overlaps ${conflict.overlap_minutes} min with another saved session.` }
          : { tone: "success", title: "Added to your agenda" },
      );
    },
    onError: (e) => toast({ tone: "error", title: e instanceof ApiError ? e.message : "Couldn't add session" }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.removeFromAgenda(id),
    onSuccess: (view, id) => {
      onDone(view);
      toast({ tone: "info", title: "Removed from your agenda", action: { label: "Undo", onClick: () => add.mutate(id) } });
    },
    onError: (e) => toast({ tone: "error", title: e instanceof ApiError ? e.message : "Couldn't remove session" }),
  });
  return { add, remove };
}

export function useSaveProfile() {
  const qc = useQueryClient();
  const keys = useKeys();
  return useMutation({
    mutationFn: (p: InterestProfile) => api.saveProfile(p),
    onSuccess: (p) => {
      qc.setQueryData(keys.profile, p);
      qc.invalidateQueries({ queryKey: ["recommendations"] });
      qc.invalidateQueries({ queryKey: keys.pathways });
    },
  });
}

export function useParseIntent() {
  const qc = useQueryClient();
  const keys = useKeys();
  return useMutation({
    mutationFn: (text: string) => api.parseIntent(text),
    onSuccess: (r) => {
      qc.setQueryData(keys.profile, r.profile);
      qc.invalidateQueries({ queryKey: ["recommendations"] });
      qc.invalidateQueries({ queryKey: keys.pathways });
    },
  });
}
