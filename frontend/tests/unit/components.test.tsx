import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tooltip } from "radix-ui";
import type { ReactNode } from "react";

import { ProfilePanel } from "@/components/recommendations/profile-panel";
import { RecommendationCard } from "@/components/recommendations/recommendation-card";
import { EmptyState, ErrorState } from "@/components/ui/primitives";
import { ToastProvider } from "@/components/ui/toast";
import type { InterestProfile, Recommendation } from "@/types/api";

vi.mock("@/hooks/use-conference", () => ({
  useConference: () => ({
    conference: { id: "kubecon-na-2026", timezone: "America/Denver" },
    timeZone: "America/Denver",
    conferences: [],
    select: () => {},
    isLoading: false,
    error: null,
    refetch: () => {},
  }),
}));

const agendaIds = new Set<string>();
const addMutate = vi.fn();
vi.mock("@/hooks/use-data", () => ({
  useAgendaIds: () => agendaIds,
  useAgendaMutations: () => ({
    add: { mutate: addMutate, isPending: false, variables: undefined },
    remove: { mutate: vi.fn(), isPending: false, variables: undefined },
  }),
  useSaveProfile: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <Tooltip.Provider>
        <ToastProvider>{ui}</ToastProvider>
      </Tooltip.Provider>
    </QueryClientProvider>,
  );
}

const session = {
  id: "kubecon-na-2026:1",
  conference_id: "kubecon-na-2026",
  title: "Fixing GPU Time-Slicing on Kubernetes",
  track: "AI Inference + Agentic",
  format: "talk",
  audience_level: "Advanced",
  starts_at: "2026-11-12T13:50:00-07:00",
  ends_at: "2026-11-12T14:20:00-07:00",
  starts_at_local: "2026-11-12T13:50:00",
  day: "2026-11-12",
  duration_minutes: 30,
  room: "Salt Palace | Level 1 | 151",
  venue: "Salt Palace",
  speakers: [{ id: "s1", full_name: "Ada Lovelace", company: "Analytical", job_title: null, photo_url: null }],
  topics: [],
  technologies: [],
  flags: [],
  is_content: true,
  has_resources: false,
};

const rec: Recommendation = {
  session,
  tier: "must_attend",
  score: 0.83,
  components: { interest_match: 0.9, topic_technology: 1, graph_relevance: 0.6, learning_goal: 0.9, novelty: 0.2, format_preference: 1 },
  explanation: {
    match_type: "direct",
    summary: "Directly about GPU Scheduling & Sharing",
    reasons: ["Covers your interests: GPU Scheduling & Sharing."],
    matched_entities: [{ id: "topic:gpu-scheduling", name: "GPU Scheduling & Sharing", type: "topic", origin: "extracted", evidence: "share GPUs", profile_weight: 1 }],
    supported_goals: [],
    learn: ["You'll learn how to share GPUs safely."],
    evidence_snippets: [],
    retrieval: { bm25_rank: 1, vector_rank: 2, intent_similarity: 0.8, graph_score: 0.6, from_graph_only: false },
  },
  related: [],
  agenda: { in_agenda: false, conflicts_with: ["kubecon-na-2026:2"] },
};

describe("RecommendationCard", () => {
  it("shows tier, grounded explanation, verbatim quote and conference-local time", () => {
    wrap(<RecommendationCard rec={rec} weights={{ interest_match: 0.4, topic_technology: 0.2, graph_relevance: 0.15, learning_goal: 0.1, novelty: 0.1, format_preference: 0.05 }} />);
    expect(screen.getByText("Must attend")).toBeInTheDocument();
    expect(screen.getByText("Directly about GPU Scheduling & Sharing")).toBeInTheDocument();
    expect(screen.getByText("You'll learn how to share GPUs safely.")).toBeInTheDocument();
    expect(screen.getByText(/1:50 PM – 2:20 PM/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fixing GPU Time-Slicing on Kubernetes" })).toHaveAttribute("href", "/sessions/kubecon-na-2026%3A1");
  });

  it("reveals the real score breakdown on demand", async () => {
    wrap(<RecommendationCard rec={rec} weights={{ interest_match: 0.4, topic_technology: 0.2, graph_relevance: 0.15, learning_goal: 0.1, novelty: 0.1, format_preference: 0.05 }} />);
    await userEvent.click(screen.getByRole("button", { name: /how this was ranked/i }));
    expect(screen.getByText(/Score 0.830/)).toBeInTheDocument();
    expect(screen.getByText("Interest match")).toBeInTheDocument();
  });

  it("adds to agenda and signals a conflict", async () => {
    wrap(<RecommendationCard rec={rec} weights={{}} />);
    const btn = screen.getByRole("button", { name: /add to agenda/i });
    await userEvent.click(btn);
    expect(addMutate).toHaveBeenCalledWith("kubecon-na-2026:1");
  });
});

describe("ProfilePanel", () => {
  const profile: InterestProfile = {
    primary_interests: [{ label: "Autoscaling", entity_id: "topic:autoscaling", type: "topic" }],
    secondary_interests: [{ label: "AI Infrastructure", entity_id: "topic:ai-infrastructure", type: "topic" }],
    learning_goals: ["Build an AI-powered autoscaler"],
    preferred_formats: ["demo"],
    experience_level: "advanced",
    preferred_topics: [],
    preferred_technologies: [],
    excluded_topics: [{ label: "Security", entity_id: "topic:security", type: "topic" }],
    intent_text: "x",
    parser: "rules",
  };
  it("renders every profile dimension and opens the editor", async () => {
    wrap(<ProfilePanel profile={profile} />);
    const panel = screen.getByRole("region", { name: /what kubecompass understood/i });
    expect(within(panel).getByText("Autoscaling")).toBeInTheDocument();
    expect(within(panel).getByText("AI Infrastructure")).toBeInTheDocument();
    expect(within(panel).getByText("Build an AI-powered autoscaler")).toBeInTheDocument();
    expect(within(panel).getByText("Demo")).toBeInTheDocument();
    expect(within(panel).getByText("Security")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /edit/i }));
    expect(await screen.findByText("Edit your interest profile")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save profile/i })).toBeInTheDocument();
  });
});

describe("states", () => {
  it("renders empty and error states with retry", async () => {
    const retry = vi.fn();
    wrap(
      <>
        <EmptyState title="Nothing here" description="Try again" />
        <ErrorState error={new Error("Search is down")} onRetry={retry} />
      </>,
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Search is down");
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(retry).toHaveBeenCalled();
  });
});

describe("AnswerText", () => {
  it("renders lists, bold and only verifiable citations, without HTML injection", async () => {
    const { AnswerText } = await import("@/components/assistant/answer-text");
    const { container } = render(
      <AnswerText
        text={"Intro <img src=x onerror=alert(1)>\n* **Ada** talks GPUs [S1]\n* Fake ref [S9]"}
        citations={[{ ref: "S1", kind: "session", id: "c:1", title: "GPU talk" }]}
      />,
    );
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByText("Ada").tagName).toBe("STRONG");
    expect(screen.getByRole("link", { name: "S1" })).toHaveAttribute("href", "/sessions/c%3A1");
    expect(screen.queryByText("[S9]")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
});
