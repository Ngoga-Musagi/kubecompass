# Knowledge graph

## Construction (`backend/app/knowledge_graph/builder.py`)
1. **Explicit**: Sessionize speakers, tracks, rooms, company answers, CNCF-Project and SubTopic tags.
   Tags map to vocabulary entries via `source_tags` (e.g. `Istio Day` → Istio, `Autoscaling` (SIG) →
   Autoscaling topic); unknown project tags become explicit project entities.
2. **Extracted**: the curated vocabulary
   (`deployment/configuration/vocabulary/cloud-native.yaml`: 45 topics, 16 technologies, ~110 projects)
   is matched against titles, abstracts and bios on word boundaries (`aliases` case-insensitive,
   `cs_aliases` case-sensitive for acronyms). Each match stores the sentence it came from.
   Confidence: title 0.95, ≥ 3 mentions 0.9, 2 mentions 0.8, 1 mention 0.65. Broad topics
   (`strict_match`) need a title hit or ≥ 2 mentions.
3. **Curated**: `parents` in the vocabulary → PART_OF edges (e.g. vLLM → Model Serving → AI Inference).
4. **Inferred**: co-occurrence (≥ 3 sessions, lift ≥ 1.5, evidence = count + example title);
   session↔session RELATED_TO = 0.6 · rescaled cosine + 0.4 · Jaccard over specific entities
   (top 6, threshold 0.35); speakers presenting a project-tagged Maintainer Track session
   WORKS_ON the project (0.75).

Duplicates keep the strongest provenance (explicit > verified > extracted > curated > ai_extracted
> inferred). Every non-explicit edge has evidence (tested).

## Storage and traversal
Edges are indexed in `conference_relationships`; the API builds a NetworkX `MultiDiGraph` read model
behind the `GraphStore` protocol (`store.py`): neighbors, personalized PageRank (α 0.75,
edge weight = confidence × min(weight, 3), room edges excluded), shortest path. Replaceable by a
graph database without changing callers (ADR 0003).

## Exploration (UI `/graph`)
Progressive: overview (top concepts per type, or the profile's; PART_OF + ≤ 2 strongest co-occurrence
links per node) → neighborhood expansion (≤ N per type, strongest first, truncation shown) →
evidence panel for each connection with origin badges → open entity/session pages.
Edge styles: solid (official), light (extracted), dotted (curated), dashed blue (inferred).

## Known limitations
- Dictionary extraction misses concepts outside the vocabulary and can over-match generic words
  (mitigated by `strict_match`, `low_signal`, case-sensitive acronyms). LLM extraction would be
  marked `ai_extracted` and is not enabled by default.
- Organization names are normalized by suffix stripping only (e.g. "Google" and "Google Cloud" stay separate).
