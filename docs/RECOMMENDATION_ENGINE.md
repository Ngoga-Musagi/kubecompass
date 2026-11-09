# Recommendation engine

```
intent text ──► InterestProfile (rules; optional Claude refinement grounded to known entities)
             ──► ES hybrid retrieval (BM25 on interest labels + kNN on intent text, RRF, filters)
             ──► graph expansion (personalized PageRank from profile entities; +40 candidates)
             ──► exclusions ("not interested in X", entity confidence ≥ 0.8)
             ──► component scores (0..1) × weights (ranking.yaml)
             ──► tiers ──► grounded explanations ──► agenda annotation (no re-ranking)
```

## Profile
`primary_interests, secondary_interests, learning_goals, preferred_formats, experience_level,
preferred_topics, preferred_technologies, excluded_topics` (+ `intent_text`, `parser`).
Rule parser: vocabulary matches in order of appearance → primary; curated parents → secondary;
goal-cue sentences → goals; format/level cue words; "not interested in / avoid / skip …" → excluded.
The LLM parser (structured output through the provider chain: Claude, OpenAI or a local Qwen via Ollama)
receives the catalog of entities present at the conference; anything it returns that isn't in the catalog
is discarded, and the rule parser's text-grounded findings are kept (they win for exclusions, level and formats). Fully editable in the UI.

## Scoring (`deployment/configuration/ranking.yaml`)
| Component | Weight | Definition |
|---|---|---|
| interest_match | 0.40 | 0.5 · BM25/maxBM25 + 0.5 · rescaled cosine(intent, session) |
| topic_technology | 0.20 | min(1, Σ profile weight × link confidence / 2) |
| graph_relevance | 0.15 | PPR score / max PPR |
| learning_goal | 0.10 | rescaled cosine(goals, session) |
| novelty | 0.10 | max(graph, semantic) × share of session entities not in the profile |
| format_preference | 0.05 | format match (1 / 0.2 / neutral 0.5) averaged with audience-level fit |

Low-signal entities (Kubernetes, Security…) are damped to 0.3 in overlap. Weights are normalized and
are **starting hypotheses**, not tuned optima.

**Tiers**: Must Attend = score ≥ 0.8 × top, has a topical match, ≤ 8, and top ≥ 0.25;
Highly Relevant = ≥ 0.6 × top, ≤ 16; Explore = novelty ≥ 0.25, not already a full topical match,
still connected (graph ≥ 0.2 or goal ≥ 0.5), ranked by 0.5·score + 0.5·novelty, ≤ 10.
Recurring titles are de-duplicated per tier.

## Explanations (`explain.py`)
Templates filled with computed values ("Covers your interests: …", "Strong keyword match (rank 3)",
"similarity 0.78", audience level, format) + **verbatim** abstract sentences for "What you'll learn"
(learning cue sentences first, else most profile-relevant). Matched entities carry origin and evidence.
`match_type`: direct / semantic / exploratory. No LLM prose about sessions or speakers.

## Feasibility
Each recommendation includes `agenda.in_agenda` and `agenda.conflicts_with`; relevance is untouched.
"Fits your schedule" (agenda page) and the assistant's "what am I missing?" use conflict-free picks.

## Evaluation
See `SEARCH_DESIGN.md`. Demo persona checks are in unit and integration tests.
