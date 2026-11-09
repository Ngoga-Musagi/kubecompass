---
description: Review current changes for correctness, architecture, security, data integrity and regressions
argument-hint: [path or git range, default: working tree]
---

Review **${ARGUMENTS:-the current working-tree diff}** for KubeCompass.

1. Get the diff (`git diff`, `git diff --staged`, or the given range/path) and read surrounding code.
2. Check, citing `file:line`:
   - **Correctness**: logic errors, timezone handling (conference IANA zone), off-by-one in ranking/pagination.
   - **Data integrity**: fabricated data, inferred info presented as explicit, missing provenance/evidence,
     unsafe refresh (could replace a valid snapshot with invalid data).
   - **Search**: filters applied to every retriever; degraded modes handled.
   - **Security**: secrets, unvalidated input, admin endpoints unprotected, unescaped HTML
     (`dangerouslySetInnerHTML` without `sanitizeHighlight`), data sent to LLM providers.
   - **Architecture**: layer violations, KubeCon literals in core logic, duplicated logic, dead code.
   - **UI**: placeholder actions, missing loading/empty/error states, token misuse, mobile overflow.
   - **Tests**: behavior changed without tests.
3. Report findings grouped by severity: **Blocker**, **Major**, **Minor**, **Nit**, each with a concrete fix.
   If nothing significant, say so plainly.
