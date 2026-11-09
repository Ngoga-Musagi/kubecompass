---
description: Analyze a feature request and produce a short, file-level implementation plan
argument-hint: <feature or change request>
---

Plan this change for KubeCompass: **$ARGUMENTS**

1. Read `CLAUDE.md` and the skills relevant to the request (`.claude/skills/*/SKILL.md`).
2. Locate the affected code with Grep/Glob. Read the actual files; do not plan from memory.
3. Identify dependencies: API contracts (`backend/app/schemas/api.py` ↔ `frontend/types/api.ts`),
   ES mappings, config YAML, docs, tests.
4. Output, in at most ~25 lines:
   - Goal and user-visible outcome.
   - Files to change/create (path → purpose).
   - Data/contract changes and migration (re-ingest needed?).
   - Tests to add (unit / integration / e2e) and how you will verify visually if UI.
   - Risks and open questions.
5. If the change is substantial (new service, contract or mapping change, > ~5 files) or ambiguous,
   **stop and ask for approval**. Otherwise say you are ready to `/implement`.
