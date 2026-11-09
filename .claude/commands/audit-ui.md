---
description: Visually inspect the running app at desktop and mobile widths, then fix visible defects
argument-hint: [page paths, default: all main pages]
---

Audit the UI. Follow the frontend-design skill.

1. Ensure the stack runs (API :8000 with ingested data, UI :3000).
2. Capture screenshots (Git Bash needs `MSYS_NO_PATHCONV=1`):
   `cd frontend && MSYS_NO_PATHCONV=1 node scripts/screenshot.mjs --fold ${ARGUMENTS:-/ /recommendations /graph /agenda /assistant /speakers /search?q=GPU}`
   Use a guest id with a profile and agenda for populated states (`--guest <uuid>`), a fresh one for
   empty states, and `--dark` for dark mode. The script flags horizontal overflow and console errors.
3. Open each PNG and check: visual hierarchy, spacing rhythm, typography scale, token consistency,
   truncation/overlap, empty/loading/error states, mobile layout (390px), contrast in dark mode,
   that every visible action works, and that no fabricated data appears.
4. Fix defects directly (smallest change in the shared component when possible), then re-capture
   and compare. Run `npm run typecheck && npm run lint && npm test`.
5. Report: issues found → fix → verified (with screenshot paths).
