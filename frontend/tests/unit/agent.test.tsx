import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";

import { AgentCards } from "@/components/agent/agent-cards";
import { PermissionChooser } from "@/components/agent/agent-permissions";
import { CalendarSection } from "@/components/agent/calendar-section";
import { ToastProvider } from "@/components/ui/toast";
import { speakable } from "@/lib/voice";
import type { AgentCard, AgentStatus } from "@/types/api";

vi.mock("@/hooks/use-conference", () => ({
  useConference: () => ({ conference: { id: "kubecon-na-2026", timezone: "America/Denver" }, timeZone: "America/Denver" }),
}));

const agentAction = vi.fn();
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  api: { agentAction: (...a: unknown[]) => agentAction(...a), calendars: () => Promise.resolve([]) },
}));

function wrap(ui: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

const session = {
  id: "kubecon-na-2026:1",
  conference_id: "kubecon-na-2026",
  title: "Fixing GPU Time-Slicing on Kubernetes",
  track: null,
  format: "talk",
  audience_level: null,
  starts_at: "2026-11-12T13:50:00-07:00",
  ends_at: "2026-11-12T14:20:00-07:00",
  starts_at_local: "2026-11-12T13:50:00",
  day: "2026-11-12",
  duration_minutes: 30,
  room: "151",
  venue: "Salt Palace",
  speakers: [],
  topics: [],
  technologies: [],
  flags: [],
  is_content: true,
  has_resources: false,
};

const status: AgentStatus = {
  conference_id: "kubecon-na-2026",
  enabled: true,
  permissions: ["read"],
  enabled_at: null,
  has_profile: false,
  audit: [],
  calendar: { configured: false, connected: false, calendar_id: null, calendar_name: null, last_sync: null, synced_sessions: 0 },
  calendar_autosync: false,
  agenda_count: 2,
  catalog: [
    { id: "read", title: "Read event information", description: "Search.", available: true, unavailable_reason: null },
    { id: "agenda", title: "Manage my agenda", description: "Propose changes.", available: true, unavailable_reason: null },
    { id: "integrations", title: "Connect external accounts", description: "Calendar.", available: false, unavailable_reason: "Coming soon." },
  ],
};

describe("voice", () => {
  it("speaks plain text without citation markers or links", () => {
    expect(speakable("Try **this** [S1] and [P2] at https://x.io now")).toBe("Try this and at now");
  });
});

describe("PermissionChooser", () => {
  it("keeps read always on and unavailable permissions locked", async () => {
    const onChange = vi.fn();
    wrap(<PermissionChooser status={status} value={[]} onChange={onChange} />);
    expect(screen.getByLabelText(/Read event information/)).toBeChecked();
    expect(screen.getByLabelText(/Read event information/)).toBeDisabled();
    expect(screen.getByLabelText(/Connect external accounts/)).toBeDisabled();
    expect(screen.getByText("Coming soon.")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/Manage my agenda/));
    expect(onChange).toHaveBeenCalledWith(["agenda"]);
  });
});

describe("AgentCards", () => {
  const confirm: AgentCard = {
    type: "action",
    title: "Please confirm",
    detail: null,
    badge: null,
    session,
    speaker: null,
    action: { tool: "add_session_to_agenda", args: { session_id: session.id }, label: "Add to agenda", description: "Add it" },
    in_agenda: false,
    fits_agenda: false,
  };

  it("runs an action only when the attendee confirms it", async () => {
    agentAction.mockResolvedValue({ reply: "Added to your agenda.", cards: [] });
    wrap(<AgentCards cards={[confirm]} />);
    expect(screen.getByText(/Overlaps a session you already saved/)).toBeInTheDocument();
    expect(agentAction).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /^Yes, add it/ }));
    expect(agentAction).toHaveBeenCalledWith("add_session_to_agenda", { session_id: session.id });
    expect(await screen.findByText("Added to your agenda.")).toBeInTheDocument();
  });

  it("cancelling makes no change", async () => {
    agentAction.mockClear();
    wrap(<AgentCards cards={[confirm]} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Okay, no changes made.")).toBeInTheDocument();
    expect(agentAction).not.toHaveBeenCalled();
  });
});

describe("CalendarSection", () => {
  it("explains when Google Calendar isn't set up on the server", () => {
    wrap(<CalendarSection status={status} pending={[]} />);
    expect(screen.getByText(/Not set up on this server yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Connect Google Calendar/ })).not.toBeInTheDocument();
  });

  it("offers to connect when configured", () => {
    const configured = { ...status, calendar: { ...status.calendar, configured: true } };
    wrap(<CalendarSection status={configured} pending={[]} />);
    expect(screen.getByRole("button", { name: /Connect Google Calendar/ })).toBeEnabled();
  });

  it("shows why a connection failed", () => {
    const configured = { ...status, calendar: { ...status.calendar, configured: true } };
    wrap(<CalendarSection status={configured} pending={[]} notice="Tick the calendar box." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Tick the calendar box.");
  });

  it("offers one-click allow-and-sync, and auto-sync only after allowing", () => {
    const connected: AgentStatus = {
      ...status,
      permissions: ["read", "integrations"],
      calendar: { ...status.calendar, configured: true, connected: true, calendar_id: "primary", calendar_name: "Me" },
    };
    const { unmount } = wrap(<CalendarSection status={connected} pending={[]} />);
    expect(screen.getByRole("button", { name: /Allow & sync my agenda now/ })).toBeEnabled();
    expect(screen.getByLabelText(/Keep my calendar updated automatically/)).toBeDisabled();
    unmount();
    wrap(<CalendarSection status={{ ...connected, permissions: ["read", "integrations", "external_actions"] }} pending={[]} />);
    expect(screen.getByRole("button", { name: /^Sync my agenda now/ })).toBeEnabled();
    expect(screen.getByLabelText(/Keep my calendar updated automatically/)).toBeEnabled();
    expect(screen.getByRole("button", { name: /Disconnect/ })).toBeEnabled();
  });
});
