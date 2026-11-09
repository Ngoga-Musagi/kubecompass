# 0006 Curated vocabulary extraction with evidence (no LLM extraction by default)

Status: accepted

**Context.** Topics/technologies/projects must be extracted; AI-extracted relations must not be
presented as facts.

**Decision.** A maintained cloud-native vocabulary (YAML) matched on word boundaries; every match
stores the source sentence. Explicit Sessionize tags map to the same entities via `source_tags`.
Hierarchy edges are `curated`; statistical edges are `inferred`.

**Consequences.** Deterministic, auditable, fast, testable. Misses concepts outside the vocabulary;
an optional LLM extractor would emit `ai_extracted` edges kept visually distinct.
