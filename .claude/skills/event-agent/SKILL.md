---
name: event-agent
description: Use when adding or changing agent tools, intents, permissions, confirmations, structured agent replies or the /api/agent endpoints. Keeps the agent authorized, grounded and testable.
---

# Event agent

## When to use
New agent capability ("ask about X", "do Y for me"), a new tool, a permission change, or any change
to `backend/app/agent/`, `backend/app/api/routes_agent.py`, `frontend/app/agent/`,
`frontend/components/agent/`. Read `docs/AGENT.md` first.

## Rules
1. **Tools wrap services; they don't reimplement them.** A tool calls search/recommendation/agenda
   services and returns a typed Pydantic model.
2. **Every tool declares a permission** and is registered in `TOOLS`. Checks happen in
   `run_tool` / `execute_confirmed`. Never check permissions only in the frontend.
3. **Profile data needs `personalization`** in every code path (see `_profile_recs`).
4. **Consequential = proposal + confirmation.** Anything that changes state the attendee owns (or,
   later, anything external) is `consequential=True`. The planner may only return a
   `ProposedAction`; `/api/agent/actions` runs it with `confirmed: true`, re-checks permissions,
   is idempotent (repeating it returns `already_done`) and records an `AuditEntry`.
5. **The LLM never picks or runs tools.** Intent routing stays deterministic until an LLM planner
   is added behind the same tool executor, with the same checks.
6. **Replies are short and speakable** (1–3 sentences, natural times like "Thursday at 1:50 PM",
   room + venue). Details go in `cards`. Never invent sessions, rooms or times; say what's missing.
7. **Event-scoped.** Tools only see `ctx.rm` (one event's read model) and that event's attendee doc.
8. New permission levels go in `CATALOG`; mark them `available=False` until they actually work.

## Checklist for a new capability
- [ ] Tool function + `Tool(...)` entry (permission, consequential flag, input model)
- [ ] Intent rule + handler method `_<intent>` in `service.py` (regex test cases for phrasing)
- [ ] Unit tests in `backend/tests/unit/test_agent.py` (routing, denial without permission)
- [ ] Integration assertion in `test_agent_authorization_tools_and_confirmed_actions` (real data)
- [ ] Card rendering in `components/agent/agent-cards.tsx` if a new card type is needed
- [ ] `TOOL_LABELS` entry in `frontend/app/agent/page.tsx` for the "How I got this" trace
- [ ] `docs/AGENT.md` tool table updated
