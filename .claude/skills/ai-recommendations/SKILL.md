---
name: ai-recommendations
description: Use when working on intent parsing, interest profiles, ranking weights, tiering, explanations or the LLM integration. Keeps recommendations explainable, configurable, grounded and evaluated.
---

# AI recommendations

## When to use
`app/recommendation/*`, `deployment/configuration/ranking.yaml`, `app/infrastructure/llm.py`,
profile/recommendation UI.

## Scope
Pipeline: intent → `InterestProfile` (rules or LLM, grounded in conference entities) → ES hybrid
retrieval → personalized PageRank expansion → component scoring → tiers → explanations →
agenda annotation (separate from relevance).

## Required inputs
Profile or intent text; the read model; `ranking.yaml`; evaluation set.

## Workflow
1. Intent: `RuleBasedIntentParser` always runs; `LLMIntentParser` (structured output via the provider
   chain: Anthropic / OpenAI / Ollama) refines it. Every interest must resolve to an existing entity id;
   rule findings are a floor and win for exclusions, level and formats.
2. Scoring components (all 0..1) and weights live in `ranking.yaml`; weights are normalized.
3. Tiers are relative to the top score with an absolute floor; Explore = novel but connected.
4. Explanations (`explain.py`) use templates filled with computed values + verbatim abstract quotes.
5. Validate with the demo persona (`tests/unit/test_search_and_recommendation.py::DEMO_INTENT`),
   `uv run pytest tests/integration -k recommendations`, and `uv run kubecompass evaluate`.

## Quality requirements
- No generated claims about session content or speaker expertise; `learn` quotes are substrings
  of the abstract (tested).
- Agenda conflicts annotate, never re-rank.
- Excluded topics remove sessions where the entity is linked with confidence ≥ 0.8.
- LLM optional: failures return rule-based results; only the user's query text and public
  conference records are sent to the provider.

## Expected outputs
Updated logic/weights with before/after evaluation numbers and screenshots of explanations.

## Common mistakes
- Tuning weights by eye without re-running the evaluation.
- Letting Kubernetes (low-signal) dominate overlap; it is damped to 0.3.
- Forgetting that `learning_goal` saturates when goals ≈ intent text.
