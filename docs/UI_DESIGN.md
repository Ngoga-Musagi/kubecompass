# UI design system

**Identity**: a compass for a dense conference. Warm paper surfaces, ink text, one vermilion
"needle" accent, editorial serif display type, mono metadata. Calm, information-dense, explainable.

## Tokens (`frontend/app/globals.css`, light + `.dark`)
| Group | Tokens |
|---|---|
| Surfaces | `bg` #f6f5f1 · `surface` #fff · `surface-2/3` · `line`, `line-strong` |
| Ink | `ink` #17171b · `ink-2` · `ink-3` · `ink-4` |
| Accent | `needle` #e2522b (+ `needle-ink`, `needle-soft`). Used for focus, primary CTA, active nav icon. |
| Tiers | `must` (needle) · `high` indigo #3a56d4 · `explore` green #0f8a62 (+ `-soft`) |
| Entities | `--ent-topic` indigo · `technology` violet · `project` green · `speaker` orange · `organization` gray · `track` magenta |
| Status | `warn` (conflicts) · `danger` · `ok` |
| Radius | cards 14px · controls 10px · chips full |
| Shadows | `--shadow-sm/md/lg` (subtle, layered) |
| Motion | `animate-rise` (420ms, staggered ≤ 8), `animate-fade`, shimmer skeletons; reduced-motion respected |

## Typography
Display: Instrument Serif (H1s, hero; italics in needle-ink for emphasis). UI: Inter 12–17px
(card titles 15–16.5px semibold, body 13–15px). Metadata: JetBrains Mono 10.5–12px; `.eyebrow` =
uppercase mono 10.5px, +0.08em tracking.

## Spacing & layout
4px base; card padding 16–20px; section gaps 40px. Desktop shell: fixed 248px sidebar, sticky
56px top bar with ⌘K search, content max 1320px; dashboards use `[1fr_340px]` with a sticky rail.
Breakpoints: Tailwind defaults (sm 640, md 768, lg 1024 sidebar, xl 1280 rails). Mobile: drawer nav,
single column, no horizontal scroll (verified by `scripts/screenshot.mjs`).

## Components
Buttons (`primary` ink, `accent` needle, `secondary`, `ghost`, `subtle`, `danger`; sm/md/lg/icon) ·
Badge tones · EntityChip (type dot + evidence tooltip) · OriginBadge (Official / From text / Curated /
Inferred) · Bearing (compass-arc relevance dial, tier-colored, value = real score) ·
SessionCard · RecommendationCard (+ "How this was ranked" breakdown) · RecommendationRow ·
ProfilePanel + ProfileEditor sheet · Sheet (side/bottom) · Toast · Segmented · EmptyState ·
ErrorState · Skeleton · CommandSearch (⌘K) · GraphCanvas (Cytoscape fcose).

## Icons
Lucide only, 16px in controls (`[&_svg]:size-4`), 12–14px inline.

## Content rules
Real data only; times in conference zone with abbreviation (MST); "Time TBA" for missing; scores
shown as dial + breakdown, never as fake percentages; every inferred element labelled.
