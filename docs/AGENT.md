# The event agent

conCompass gives every attendee a personal agent for one event. It is an authorized, tool-using
agent over the event's official data, not a chatbot bolted onto a website. Code:
`backend/app/agent/`, `backend/app/api/routes_agent.py`, `frontend/app/agent/`,
`frontend/components/agent/`, `frontend/lib/voice.ts`.

## Request flow
```
text or voice ─▶ POST /api/agent/chat
                 │ 1. agent enabled for this event?           (403 agent_disabled otherwise)
                 │ 2. classify intent (deterministic rules)    next_session · free_time · happening_now
                 │                                             build_agenda · show_agenda · conflicts
                 │                                             add · remove · recommend · ask
                 │ 3. run read tools, each permission-checked  (ToolDenied → "permission needed" reply)
                 │ 4. open questions → grounded RAG answerer   (cites [S#]/[P#]; uncited LLM text dropped)
                 ▼
            AgentReply { reply (short, speakable), cards[], citations[], trace[], needs_permission }
                 │ cards may carry a ProposedAction (add/remove); nothing changes yet
                 ▼
attendee clicks "Yes, add it" ─▶ POST /api/agent/actions {tool, args, confirmed: true}
                 │ re-checks enablement + permission, runs the tool idempotently, writes an audit entry
```
The LLM never chooses or runs tools, so instructions hidden in session abstracts cannot trigger
actions. A tool-calling LLM planner can replace step 2 later without changing the tools.

## Permissions
Stored per attendee **per event** in `conference_attendees` (`agent` field), off by default.

| Level | Grants | Status |
|---|---|---|
| `read` | search sessions/speakers/schedule, answer questions | implied when enabled |
| `personalization` | use the attendee's interests/goals for ranking | grantable |
| `agenda` | read the agenda, find conflicts/free time, *propose* changes | grantable; each change confirmed |
| `integrations` | connect Google Calendar, list writable calendars | available when the server has Google configured ([setup](GOOGLE_CALENDAR.md)) |
| `external_actions` | sync saved sessions to the connected calendar | available once connected; each sync confirmed |

Enforcement is in `app/agent/tools.py` (`run_tool`, `execute_confirmed`, and `_profile_recs`,
which never uses the profile without `personalization`). The UI only displays the state.
Disabling the agent revokes every permission. `DELETE /api/agent/memory` clears interests and goals.
The attendee can see the last 20 confirmed actions in the permissions sheet.

## Tools
| Tool | Permission | Consequential |
|---|---|---|
| `search_sessions`, `search_speakers`, `get_session_details` | read | no |
| `sessions_in_free_time` (starts within 30 min, ends inside the window, no agenda overlap) | read | no |
| `recommend_sessions`, `suggest_agenda` (greedy conflict-free plan around saved sessions) | personalization | no |
| `get_user_agenda`, `next_session`, `check_schedule_conflicts` | agenda | no |
| `add_session_to_agenda`, `remove_session_from_agenda` | agenda | **yes**: proposal + confirmation, idempotent, audited |
| `sync_agenda_to_calendar` ("sync my agenda to Google Calendar") | external_actions | **yes**: same rules; see [GOOGLE_CALENDAR.md](GOOGLE_CALENDAR.md) |

Each tool has a typed Pydantic input. Adding a tool: write the function, register a `Tool(...)`
with its permission and `consequential` flag, route an intent to it in `service.py`, add tests.

## Voice
Browser speech recognition (push-to-talk, one utterance per tap, never background listening) and
`speechSynthesis` for replies, behind `SpeechInput` / `SpeechOutput` interfaces in
`frontend/lib/voice.ts`. Either side can be swapped for a server provider independently.
- A question asked by voice is answered by voice; any reply can be replayed with **Listen**.
- Low-confidence transcripts (noisy halls) go into the text box for review instead of being sent.
- Recognition errors (no speech, blocked mic, no network) get plain-language messages; unsupported
  browsers hide the mic and keep text.
- Replies are short and free of citation markers so they sound natural; details live in cards.

## Time
"Now" is the server clock in UTC, rendered in the event's IANA zone. `AgentChatRequest.now` can
override it for demos and tests (e.g. `2026-11-10T08:30:00-07:00`).

## Tests
- `backend/tests/unit/test_agent.py`: intent routing, parsing, grants, server-side denial,
  "consequential tools only run through confirmation", spoken formatting.
- `backend/tests/integration/test_full_journey.py::test_agent_authorization_tools_and_confirmed_actions`:
  the full flow against real Elasticsearch and the real KubeCon data.
- `frontend/tests/unit/agent.test.tsx` and `frontend/tests/e2e/journey.spec.ts` (desktop + mobile).
