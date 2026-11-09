# 0005 Local embeddings, optional LLM with deterministic fallbacks

Status: accepted

**Decision.** Embeddings: FastEmbed `BAAI/bge-small-en-v1.5` (384-d, ONNX, CPU) behind an
`EmbeddingProvider` interface: no API key, no attendee text leaves the server, and it's fast enough
for 600 sessions. LLM: Anthropic Claude (`claude-opus-5-5`, low effort; server-side fallback) behind
`LLMProvider`, used only for intent refinement and assistant prose. Without credentials, the
rule-based parser and extractive assistant are used and the UI says so.

**Update (2026-11-09).** LLM access is now a provider chain (`ChainLLMProvider`): Anthropic, OpenAI
and Ollama/any OpenAI-compatible server (one `OpenAICompatibleProvider` on the official `openai` SDK),
ordered by `KUBECOMPASS_LLM_PROVIDER` (`auto` = anthropic → openai → ollama). Failures fall through;
permanent failures (credentials, credits, unknown model) pause a provider for 10 min. Measured on an
RTX 5070 Laptop (8 GB): qwen3.5:4b with `reasoning_effort=none` ≈ 1.5 s structured intent / 3–5 s
assistant answer (with reasoning on: ~120 s); qwen2.5:3b ≈ 2 s; qwen3-vl:4b ≈ 10 s. Because small local
models over-generalize, the LLM profile is merged with the rule parser (rules win for exclusions,
level and formats; interests are a union), and assistant answers that cite no provided record are
discarded in favour of the retrieval-only answer.

**Consequences.** The full demo runs offline after the one-time model download. Calibrated
thresholds (cosine compression) are documented in SEARCH_DESIGN.md and must be re-measured if
the model changes.
