import type {
  AgendaView,
  AgentPermission,
  AgentReply,
  AgentStatus,
  CalendarOption,
  CalendarStatus,
  Alternative,
  ChatResponse,
  ConferenceInfo,
  EntityDetail,
  GraphResponse,
  Health,
  IdentityOut,
  IntentResponse,
  InterestProfile,
  Page,
  Pathway,
  RecommendationResponse,
  SearchMode,
  SearchResponse,
  SessionDetail,
  SessionFilters,
  SessionSummary,
  SpeakerDetail,
  SpeakerOut,
  Suggestions,
} from "@/types/api";
import { getGuestId } from "@/lib/guest";

// Empty string = same origin (single-container deploys proxy /api to the backend via next.config).
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | string[] | undefined | null>;

/** Selected conference; every request is scoped to it (multi-conference support). */
let currentConference: string | null = null;
export function setApiConference(id: string | null) {
  currentConference = id;
}

function qs(query?: Query): string {
  const p = new URLSearchParams();
  if (currentConference) p.set("conference", currentConference);
  if (!query) return p.toString() ? `?${p}` : "";
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init: RequestInit & { query?: Query } = {}): Promise<T> {
  const { query, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}${qs(query)}`, {
      ...rest,
      headers: {
        "Content-Type": "application/json",
        "X-Guest-Id": getGuestId(),
        ...headers,
      },
    });
  } catch {
    throw new ApiError(0, "network", "Can't reach the conCompass API. Is the backend running?");
  }
  if (!res.ok) {
    let code = "error";
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<Health>("/api/health"),
  agent: () => request<AgentStatus>("/api/agent"),
  setAgent: (enabled: boolean, permissions: AgentPermission[] = []) =>
    request<AgentStatus>("/api/agent", { method: "PUT", body: JSON.stringify({ enabled, permissions }) }),
  clearAgentMemory: () => request<AgentStatus>("/api/agent/memory", { method: "DELETE" }),
  agentChat: (message: string, history: { role: "user" | "assistant"; content: string }[], contextSessionId?: string) =>
    request<AgentReply>("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({ message, history, context_session_id: contextSessionId ?? null }),
    }),
  agentAction: (tool: string, args: Record<string, string>) =>
    request<AgentReply>("/api/agent/actions", { method: "POST", body: JSON.stringify({ tool, args, confirmed: true }) }),
  calendarConnect: () => request<{ auth_url: string }>("/api/integrations/google/connect", { method: "POST" }),
  calendars: () => request<CalendarOption[]>("/api/integrations/google/calendars"),
  chooseCalendar: (calendarId: string) =>
    request<CalendarStatus>("/api/integrations/google/calendar", { method: "PUT", body: JSON.stringify({ calendar_id: calendarId }) }),
  disconnectCalendar: () => request<CalendarStatus>("/api/integrations/google", { method: "DELETE" }),
  identify: (handle: string) =>
    request<IdentityOut>("/api/identity", { method: "POST", body: JSON.stringify({ handle }) }),
  conferences: () => request<ConferenceInfo[]>("/api/conferences"),
  conference: (id: string) => request<ConferenceInfo>(`/api/conferences/${enc(id)}`),

  sessions: (query: Query) => request<Page<SessionSummary>>("/api/sessions", { query }),
  session: (id: string) => request<SessionDetail>(`/api/sessions/${enc(id)}`),
  sessionAlternatives: (id: string) => request<Alternative[]>(`/api/agenda/alternatives/${enc(id)}`),

  speakers: (query: Query) => request<Page<SpeakerOut>>("/api/speakers", { query }),
  speaker: (id: string) => request<SpeakerDetail>(`/api/speakers/${enc(id)}`),

  parseIntent: (text: string) =>
    request<IntentResponse>("/api/discovery/intent", {
      method: "POST",
      body: JSON.stringify({ text, save: true }),
    }),
  profile: () => request<InterestProfile | null>("/api/profile"),
  saveProfile: (profile: InterestProfile) =>
    request<InterestProfile>("/api/profile", { method: "PUT", body: JSON.stringify(profile) }),
  search: (body: { query: string; filters?: SessionFilters; mode?: SearchMode; limit?: number; offset?: number }) =>
    request<SearchResponse>("/api/discovery/search", { method: "POST", body: JSON.stringify(body) }),
  suggest: (q: string) => request<Suggestions>("/api/discovery/suggest", { query: { q } }),
  pathways: () => request<Pathway[]>("/api/discovery/pathways"),
  recommendations: (filters?: SessionFilters) =>
    request<RecommendationResponse>("/api/recommendations", {
      method: "POST",
      body: JSON.stringify({ filters: filters ?? {} }),
    }),

  graphOverview: (query?: Query) => request<GraphResponse>("/api/knowledge-graph", { query }),
  graphNeighborhood: (id: string, query?: Query) =>
    request<GraphResponse>(`/api/knowledge-graph/neighborhood/${enc(id)}`, { query }),
  graphEntity: (id: string) => request<EntityDetail>(`/api/knowledge-graph/entities/${enc(id)}`),
  graphSearch: (q: string) =>
    request<{
      entities: { id: string; type: string; name: string; session_count: number }[];
      speakers: { id: string; type: string; name: string; session_count: number }[];
    }>("/api/knowledge-graph/search", { query: { q } }),

  agenda: () => request<AgendaView>("/api/agenda"),
  addToAgenda: (session_id: string) =>
    request<AgendaView>("/api/agenda/sessions", { method: "POST", body: JSON.stringify({ session_id }) }),
  removeFromAgenda: (session_id: string) =>
    request<AgendaView>(`/api/agenda/sessions/${enc(session_id)}`, { method: "DELETE" }),
  acknowledgeChanges: () => request<AgendaView>("/api/agenda/acknowledge-changes", { method: "POST" }),
  agendaIcsUrl: () => `${API_URL}/api/agenda/export/ics`,

  chat: (message: string, history: { role: "user" | "assistant"; content: string }[], context_session_id?: string) =>
    request<ChatResponse>("/api/assistant/chat", {
      method: "POST",
      body: JSON.stringify({ message, history, context_session_id }),
    }),
};

/** Download the agenda as .ics (needs the guest header, so a plain link won't do). */
export async function downloadIcs(filename: string): Promise<void> {
  const res = await fetch(api.agendaIcsUrl(), { headers: { "X-Guest-Id": getGuestId() } });
  if (!res.ok) throw new ApiError(res.status, "export_failed", "Calendar export failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
