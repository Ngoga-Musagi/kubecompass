# Data model

Designed from the actual Sessionize payloads (inspected 2026-11-09 with
`scripts/inspect_sessionize.py`), not from assumptions.

## Source payloads
| File / endpoint | Shape | Count |
|---|---|---|
| `kubecon-all.json` (`/view/All`) | `{sessions, speakers, questions, categories, rooms}` | 600 sessions, 712 speakers, 11 questions, 7 categories, 37 rooms |
| `kubecon-speakers.json` (`/view/Speakers`) | array of speakers with inline `{id, question, answer}` and `sessions: [{id, name}]` | 712 (same ids) |

Categories (by title): **All Sessions** (30 tracks, incl. Keynote, Lightning, Tutorials,
Contribfest, Posters, Breaks, Registration, co-located events), **Audience Level**
(Beginner/Advanced/Any Level, on 219 sessions), **SubTopic** (co-located event names, BoF, Network
Nook), **CNCF Projects** (104 tags, many are Kubernetes SIG names), **End User Programming**,
**Is Sponsored Keynote**, **Solutions Showcase Programming**.
Questions used: Company, Company Override, Speaker Title, Presentation Slides (111), GitHub
Repository (9), Project Demo (3), Website (29), Location Map (15).

Data-quality findings: 47 sessions without abstract; 100 without speakers (logistics, stages);
10 titles reused across distinct sessions (recurring slots, kept); 3 speaker names shared by
different people (distinct ids); 17 speakers without company; no recording/live URLs; all times
are naive local wall-clock times; no duplicate ids.

## Canonical entities (`backend/app/domain/models.py`)
- **Conference**: id, name, city, IANA timezone, dates, counts, data version, last refresh.
- **Session**: `id = {conference}:{source_id}`, title, description (verbatim), track, subtopics,
  audience_level, `format` + `format_origin` (category | subtopic | title_pattern | default),
  flags (end_user, sponsored, learning_lounge), project_tags (explicit), speakers, `TimeSlot`,
  `Room`, resources, `entities: EntityRef[]`, `is_content`, `provenance`.
- **TimeSlot**: `starts_at_local` (as in source), `starts_at` (tz-aware, conference zone),
  `timezone`, `day`, `duration_minutes`. Missing times → `time = None`.
- **Speaker**: full name, tagline, bio, company (Company Override > Company), job title, photo,
  links, session ids, bio-derived entities, provenance.
- **Entity**: `{type}:{slug}` for topic | technology | project | organization | track | room;
  origin, session/speaker counts.
- **Relationship**: source/target ids+types, `type`, `origin`, `method`, `confidence`, `evidence`, `weight`.
- **Resource**: kind (slides, repository, demo, website, location_map, recording), url.
- **Provenance**: source system/id/url, ingested_at, ingestion_version, payload sha256.

## Relationship types
| Type | From → To | Origin / method |
|---|---|---|
| PRESENTS | speaker → session | explicit / sessionize_field |
| ASSOCIATED_WITH | speaker → organization | explicit / sessionize_question (placeholder values like "Maintainer" excluded) |
| BELONGS_TO_TRACK | session → track | explicit / sessionize_category |
| SCHEDULED_IN | session → room | explicit / sessionize_field |
| DISCUSSES / USES / COVERS | session → project / technology / topic | explicit (Sessionize tags) or extracted (vocabulary_match, with sentence) |
| WORKS_ON | speaker → project/technology | extracted (bio sentence with role word) or inferred (maintainer_track_session) |
| RELATED_TO | speaker → tech | extracted (bio mention, conf 0.6) |
| RELATED_TO | entity ↔ entity | inferred (co_occurrence: ≥ 3 sessions, lift ≥ 1.5) |
| RELATED_TO | session ↔ session | inferred (embedding_and_entity_overlap) |
| PART_OF | tech/project/topic → topic | curated (vocabulary_hierarchy) |

Current graph (2026-11-09): 1,814 nodes (45 topics, 16 technologies, 106 projects, 269 orgs,
30 tracks, 36 rooms, 600 sessions, 712 speakers) and 9,249 relationships: 2,929 explicit,
3,054 extracted, 147 curated, 3,119 inferred (2,162 session↔session).

## Attendee state (`conference_attendees`)
`{conference_id, guest_id, profile: InterestProfile, agenda: {items: [{session_id, added_at,
snapshot{title, starts_at_local, ends_at_local, room}, note, position}]}, updated_at}`.
The snapshot enables change notices and future calendar sync.
