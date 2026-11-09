---
name: frontend-design
description: Use for any KubeCompass UI work (new page, component, layout, state, styling). Enforces the design system, real-data rendering, responsive behavior and designed loading/empty/error states.
---

# Frontend design

## When to use
Any change under `frontend/app` or `frontend/components`, or anything a user will see.

## Scope
Next.js 15 App Router, React 19, Tailwind v4 tokens (`app/globals.css`), Radix primitives,
Lucide icons only, TanStack Query for data, Cytoscape for the graph.

## Required inputs
`docs/UI_DESIGN.md` (tokens, type scale, components), the API contract in `frontend/types/api.ts`.

## Workflow
1. Reuse before creating: `components/ui/{button,primitives,sheet,toast}.tsx`,
   `components/sessions/session-parts.tsx` (EntityChip, OriginBadge, SessionMeta, AgendaButton,
   Bearing, TIER_COPY), `SessionCard`, `RecommendationCard`.
2. Use semantic tokens only (`bg-surface`, `text-ink-2`, `border-line`, `text-needle`, tier colors,
   `--ent-*`). Never hard-code hex values in components.
3. Typography: display headings `font-display` (Instrument Serif) sparingly; UI text Inter 12–17px;
   metadata `.eyebrow` / mono. One H1 per page.
4. Data via hooks in `hooks/use-data.ts` / `use-conference.tsx`; query keys include the conference.
5. Every async view needs: skeleton (`<Skeleton/>`), `ErrorState` with retry, `EmptyState` with a
   next action. Every button must do something real.
6. Times: `formatTime/formatTimeRange(…, timeZone)` from `lib/format.ts` with the conference zone.
7. Responsive: grid children get `min-w-0`; test at 390px. No horizontal page scroll.
8. Verify: `npm run typecheck && npm run lint && npm test`, then screenshots
   (`MSYS_NO_PATHCONV=1 node scripts/screenshot.mjs --fold /your-page`) and look at them.

## Quality requirements
- Information-dense but calm cards: title, time/room, speakers, why-it-matches, up to 6 chips.
- Inferred/extracted information is labelled with `OriginBadge`; evidence available on hover.
- Accessible: labelled inputs, `aria-current` nav, focus-visible rings, reduced-motion respected.
- Dark mode works (tokens redefined under `.dark`).

## Expected outputs
Polished, consistent UI with tests for meaningful behavior and before/after screenshots reviewed.

## Common mistakes
- Fabricated numbers ("95% match", fake stats). Scores shown are the real computed values.
- Rendering times with the browser's locale zone.
- `dangerouslySetInnerHTML` without `sanitizeHighlight`.
- Cards inside CSS grid without `min-w-0` (causes mobile overflow).
- Cytoscape container with `absolute inset-0` directly (Cytoscape forces `position: relative`).
