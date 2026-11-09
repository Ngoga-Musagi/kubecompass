---
name: agenda-management
description: Use for personal agenda features: saving sessions, conflicts, room transitions, gaps, alternatives, schedule-change notices, timezone handling and .ics export.
---

# Agenda management

## When to use
`app/agenda/*`, `app/calendar/ics.py`, `/api/agenda*`, `frontend/app/agenda`.

## Scope
Guest attendee state (profile + agenda) in the `conference_attendees` index keyed by
`{conference}:{X-Guest-Id}`. Each saved item keeps a snapshot (title, local start/end, room)
so later schedule changes surface as notices.

## Required inputs
Read model sessions (`time.starts_at` tz-aware), conference timezone, attendee state.

## Workflow
1. Pure logic lives in `scheduling.py` (overlaps, tight transitions between venues, gaps); test it
   with explicit `America/Denver` datetimes.
2. Alternatives: recurring same-title slots > graph RELATED_TO > shared specific entities >
   very similar abstracts (cosine ≥ 0.82); fitting ones first.
3. ICS: TZID + generated VTIMEZONE from zoneinfo transitions; RFC 5545 escaping and folding.
   Validate with `tests/unit/test_agenda_and_calendar.py`.
4. Show the seating notice wherever an agenda is presented and in exported events.

## Quality requirements
- Never hardcode offsets; Nov 2026 in Salt Lake City is MST (UTC−7) after DST ended Nov 1.
- Touching sessions (end == start) do not conflict.
- 409 for duplicate saves, 404 for unknown sessions, UUID-validated guest ids.

## Expected outputs
Correct conflict/gap/transition data, importable `.ics`, tests.

## Common mistakes
- Rendering agenda times in the viewer's zone.
- Writing UTC times without `Z` or local times without `TZID`.
- Lowering recommendation scores for conflicts (relevance ≠ feasibility).
