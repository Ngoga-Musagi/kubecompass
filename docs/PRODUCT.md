# Product

**KubeCompass** turns a conference schedule into intent-driven knowledge discovery.

> Tell KubeCompass what you want to learn. It discovers the sessions, speakers, technologies and
> projects that matter to you, explains why they matter, and helps you make the most of your conference.

First target: KubeCon + CloudNativeCon North America 2026 (Salt Lake City, Nov 8–12, `America/Denver`).
Data: the official public Sessionize endpoints (600 sessions, 712 speakers as of 2026-11-09).

## Users and jobs
| Attendee | Job to be done |
|---|---|
| Engineer with a concrete project | "Find the talks that help me build X, and why." |
| Platform/team lead | "Cover our stack's topics and find the people to talk to." |
| Newcomer | "Find beginner-friendly sessions without drowning in 555 talks." |

## Capabilities
1. **AI-powered discovery**: natural-language intent → editable profile; hybrid (BM25 + vector, RRF)
   search with structured filters; ⌘K autocomplete.
2. **Conference knowledge graph**: sessions, speakers, topics, technologies, projects,
   organizations, tracks, with evidence and provenance on every edge.
3. **Explainable recommendations**: Must Attend / Highly Relevant / Explore tiers, component score
   breakdown, verbatim "what you'll learn" quotes, related sessions.
4. **Personal agenda**: save sessions, conflicts, tight building changes, gaps, alternatives,
   schedule-change notices, `.ics` export (TZID + VTIMEZONE). A saved session never reserves a seat.
5. **Conference assistant**: retrieval-augmented answers with [S#]/[P#] citations, agenda-aware
   ("what am I missing?"), honest "not in the data" responses; works without an LLM.
6. **Multi-conference**: canonical model + adapters + per-conference YAML.

## Screens
Discover (default) · Recommendations · Knowledge Graph · Speakers (+ detail) · My Agenda ·
Assistant · Session detail · Topic/technology/project knowledge pages · Search.

## Demo scenario (all on real data; covered by `frontend/tests/e2e/journey.spec.ts`)
1. **Intent**: paste the "AI-powered Kubernetes autoscaler" persona on Discover.
2. **Profile**: KubeCompass shows main interests (Autoscaling, GPU Scheduling & Sharing,
   AI Inference, Agentic AI, Observability…), related areas, goals, formats (demo, talk), level (advanced).
3. **Discovery**: hybrid retrieval from Elasticsearch (pipeline footer shows counts and ms).
4. **Knowledge expansion**: personalized PageRank adds graph-only candidates.
5. **Recommendations**: tiered cards with reasons, quotes, chips with evidence, ranking breakdown.
6. **Exploration**: open a chip (e.g. *GPU Scheduling & Sharing*) or `/graph`; follow connections.
7. **Agenda**: add sessions; toasts flag conflicts.
8. **Conflict resolution**: My Agenda → *Alternatives* (recurring slots, related, similar; fitting first).
9. **Calendar**: *Export .ics* → import into any calendar.

## Non-goals (MVP)
Accounts/auth (guest UUID instead), seat reservation, push notifications (change notices are
shown in-app), Kubernetes deployment of KubeCompass itself.
