// Mirrors backend/app/schemas/api.py and service response models. Keep in sync (docs/API.md).

export type EntityType =
  | "session"
  | "speaker"
  | "topic"
  | "technology"
  | "project"
  | "organization"
  | "track";
export type Origin = "explicit" | "extracted" | "ai_extracted" | "inferred" | "curated" | "verified";

export interface EntityRef {
  id: string;
  name: string;
  type: EntityType;
  origin: Origin;
  confidence: number;
  evidence: string | null;
}

export interface Resource {
  kind: string;
  url: string;
  title: string | null;
}

export interface SpeakerBrief {
  id: string;
  full_name: string;
  company: string | null;
  job_title: string | null;
  photo_url: string | null;
}

export interface SessionSummary {
  id: string;
  conference_id: string;
  title: string;
  track: string | null;
  format: string;
  audience_level: string | null;
  starts_at: string | null;
  ends_at: string | null;
  starts_at_local: string | null;
  day: string | null;
  duration_minutes: number | null;
  room: string | null;
  venue: string | null;
  speakers: SpeakerBrief[];
  topics: EntityRef[];
  technologies: EntityRef[];
  flags: string[];
  is_content: boolean;
  has_resources: boolean;
}

export interface RelatedSession {
  session: SessionSummary;
  evidence: string | null;
  confidence: number;
  origin: Origin;
}

export interface SessionDetail extends SessionSummary {
  description: string | null;
  subtopics: string[];
  format_origin: string;
  entities: EntityRef[];
  resources: Resource[];
  source: {
    system: string | null;
    source_id: string | null;
    source_url: string | null;
    ingested_at: string | null;
    ingestion_version: string | null;
  };
  related: RelatedSession[];
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface ConferenceInfo {
  id: string;
  name: string;
  short_name: string;
  city: string;
  timezone: string;
  website: string | null;
  schedule_url: string | null;
  start_date: string | null;
  end_date: string | null;
  days: string[];
  session_count: number;
  content_session_count: number;
  speaker_count: number;
  tracks: FacetValue[];
  formats: FacetValue[];
  data_version: string | null;
  last_refreshed_at: string | null;
  source_system: string;
}

export interface Health {
  status: "ok" | "degraded";
  elasticsearch: string;
  embeddings: string;
  llm: string;
  indexed_conferences: string[];
}

export type SearchMode = "keyword" | "vector" | "hybrid" | "hybrid_native";

export interface SessionFilters {
  days?: string[];
  tracks?: string[];
  formats?: string[];
  audience_levels?: string[];
  speaker_ids?: string[];
  entity_ids?: string[];
  include_non_content?: boolean;
}

export interface SearchHit {
  session: SessionSummary;
  score: number;
  bm25_rank: number | null;
  vector_rank: number | null;
  vector_similarity: number | null;
  highlights: string[];
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  total: number;
  took_ms: number;
  degraded: string[];
  hits: SearchHit[];
  facets: Record<string, FacetValue[]>;
}

export interface ProfileInterest {
  label: string;
  entity_id: string | null;
  type: string | null;
}

export type ExperienceLevel = "beginner" | "intermediate" | "advanced" | "any";

export interface InterestProfile {
  primary_interests: ProfileInterest[];
  secondary_interests: ProfileInterest[];
  learning_goals: string[];
  preferred_formats: string[];
  experience_level: ExperienceLevel;
  preferred_topics: ProfileInterest[];
  preferred_technologies: ProfileInterest[];
  excluded_topics: ProfileInterest[];
  intent_text: string | null;
  parser: "rules" | "llm" | "manual";
}

export interface IntentResponse {
  profile: InterestProfile;
  parser: string;
  llm_available: boolean;
}

export interface MatchedEntity {
  id: string;
  name: string;
  type: string;
  origin: Origin;
  evidence: string | null;
  profile_weight: number;
}

export interface Explanation {
  match_type: "direct" | "semantic" | "exploratory";
  summary: string;
  reasons: string[];
  matched_entities: MatchedEntity[];
  supported_goals: string[];
  learn: string[];
  evidence_snippets: string[];
  retrieval: {
    bm25_rank: number | null;
    vector_rank: number | null;
    intent_similarity: number | null;
    graph_score: number;
    from_graph_only: boolean;
  };
}

export type Tier = "must_attend" | "highly_relevant" | "explore";

export interface Recommendation {
  session: SessionSummary;
  tier: Tier;
  score: number;
  components: Record<string, number>;
  explanation: Explanation;
  related: SessionSummary[];
  agenda: { in_agenda: boolean; conflicts_with: string[] };
}

export interface InsightItem {
  id: string;
  name: string;
  type: string;
  count: number;
  detail: string | null;
}

export interface RecommendationResponse {
  conference_id: string;
  generated_at: string;
  profile: InterestProfile;
  must_attend: Recommendation[];
  highly_relevant: Recommendation[];
  explore: Recommendation[];
  insights: {
    top_topics: InsightItem[];
    related_technologies: InsightItem[];
    speakers: { speaker: SpeakerBrief; reason: string; origin: Origin }[];
    new_discoveries: string[];
  };
  weights: Record<string, number>;
  pipeline: Record<string, number | string>;
  degraded: string[];
}

export interface GraphNode {
  id: string;
  type: EntityType;
  name: string;
  session_count: number | null;
  meta: Record<string, string | null>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  origin: Origin;
  method: string;
  confidence: number;
  evidence: string | null;
}

export interface GraphResponse {
  center: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: Record<string, number>;
}

export interface EntityDetail {
  entity: GraphNode;
  origin: Origin;
  sessions: RelatedSession[];
  speakers: SpeakerBrief[];
  related: GraphNode[];
  parents: GraphNode[];
  children: GraphNode[];
}

export interface Pathway {
  entity: GraphNode;
  session_count: number;
  profile_match: boolean;
  children: GraphNode[];
  sample_sessions: SessionSummary[];
}

export interface SpeakerOut extends SpeakerBrief {
  tagline: string | null;
  bio: string | null;
  is_top_speaker: boolean;
  links: Resource[];
  expertise: EntityRef[];
  session_count: number;
}

export interface SpeakerDetail extends SpeakerOut {
  sessions: SessionSummary[];
  works_on: EntityRef[];
  related_speakers: SpeakerBrief[];
}

export interface ChangeNotice {
  session_id: string;
  title: string;
  kind: "modified" | "removed";
  fields: string[];
  before: Record<string, string | null>;
  after: Record<string, string | null>;
}

export interface AgendaEntry {
  session: SessionSummary;
  added_at: string;
  conflicts_with: string[];
  change: ChangeNotice | null;
  position: number;
}

export interface AgendaView {
  conference_id: string;
  timezone: string;
  total: number;
  days: { day: string; entries: AgendaEntry[]; gaps: { day: string; start: string; end: string; minutes: number }[] }[];
  unscheduled: AgendaEntry[];
  conflicts: { session_ids: string[]; titles: string[]; overlap_minutes: number }[];
  transitions: { from_session_id: string; to_session_id: string; gap_minutes: number; reason: string }[];
  notices: ChangeNotice[];
  seating_notice: string;
  data_version: string;
}

export interface Alternative {
  session: SessionSummary;
  reason: string;
  fits_agenda: boolean;
  origin: Origin;
}

export interface Citation {
  ref: string;
  kind: "session" | "speaker";
  id: string;
  title: string;
}

export interface ChatResponse {
  answer: string;
  mode: "llm" | "retrieval_only" | "no_results";
  intent: string;
  sessions: SessionSummary[];
  speakers: SpeakerBrief[];
  citations: Citation[];
  concepts: { id: string; name: string; type: string; relation: string; origin: Origin; evidence: string | null }[];
  notice: string | null;
  generated_by: string | null;
}

export interface Suggestions {
  sessions: { id: string; title: string; track: string | null; starts_at_local: string | null }[];
  speakers: { id: string; full_name: string; company: string | null }[];
  entities: { id: string; type: EntityType; name: string; session_count: number }[];
}

export interface IdentityOut {
  attendee_id: string;
  kind: "email" | "username";
  display: string;
}

// ---- Event agent -------------------------------------------------------------------------------
export type AgentPermission = "read" | "personalization" | "agenda" | "integrations" | "external_actions";

export interface PermissionInfo {
  id: AgentPermission;
  title: string;
  description: string;
  available: boolean;
  unavailable_reason: string | null;
}

export interface AgentAuditEntry {
  at: string;
  tool: string;
  args: Record<string, unknown>;
  outcome: string;
  detail: string | null;
}

export interface AgentStatus {
  conference_id: string;
  enabled: boolean;
  permissions: AgentPermission[];
  enabled_at: string | null;
  catalog: PermissionInfo[];
  has_profile: boolean;
  audit: AgentAuditEntry[];
  calendar: CalendarStatus;
  calendar_autosync: boolean;
  agenda_count: number;
}

export interface CalendarSyncSummary {
  at: string;
  created: number;
  updated: number;
  deleted: number;
  unchanged: number;
  failed: number;
  failures: string[];
}

export interface CalendarStatus {
  configured: boolean;
  connected: boolean;
  calendar_id: string | null;
  calendar_name: string | null;
  last_sync: CalendarSyncSummary | null;
  synced_sessions: number;
}

export interface CalendarOption {
  id: string;
  name: string;
  primary: boolean;
}

export interface ProposedAction {
  tool: string;
  args: Record<string, string>;
  label: string;
  description: string;
}

export interface AgentCard {
  type: "session" | "speaker" | "conflict" | "agenda_summary" | "action" | "notice";
  title: string | null;
  detail: string | null;
  badge: string | null;
  session: SessionSummary | null;
  speaker: SpeakerBrief | null;
  action: ProposedAction | null;
  in_agenda: boolean;
  fits_agenda: boolean | null;
}

export interface AgentReply {
  reply: string;
  intent: string;
  cards: AgentCard[];
  trace: { tool: string; status: "ok" | "denied" | "error"; detail: string | null }[];
  needs_permission: AgentPermission | null;
  mode: "agent" | "llm" | "retrieval_only" | "no_results";
  citations: Citation[];
  generated_by: string | null;
}
