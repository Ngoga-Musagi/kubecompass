# Search design

## Indices and mappings (`elasticsearch/`)
Per conference, ingestion writes versioned indices
`conference_<kind>__<conference>__<version>` and swaps the read alias `conference_<kind>`.
Mappings are `dynamic: strict`.

- **sessions**: `title` (english analyzer, search-time synonyms, `.keyword`, `.sayt`),
  `description`, `entity_names`, `speaker_names`, keyword facets (`track`, `format`, `day`,
  `audience_level`, `topics`, `technologies`, `projects`, `entity_ids`, `speaker_ids`), dates,
  `is_content`, `embedding` (`dense_vector`, 384-d, cosine, HNSW), and the canonical record in a
  non-indexed `doc` object.
- **speakers**: name (`.sayt`), company, tagline, bio, session titles, entity names, embedding.
- **entities** (autocomplete, `name.sayt`), **relationships** (graph edges with evidence),
  **attendees**, **changes**.
- Analysis: possessive + lowercase + **synonym_graph** (k8s↔kubernetes, otel, wasm, MCP, DRA,
  HPA/VPA, IDP, SRE, RAG, SBOM, eBPF, agentic…) at search time + stop + english stemmer.

## Retrieval
| Mode | Implementation |
|---|---|
| keyword (BM25) | `multi_match` best_fields (title^3, entity_names^2, description, speakers^1.5, tags) + title/description phrase boosts + exact title; `"quoted"` → mandatory phrase |
| vector | kNN on `embedding`, `num_candidates = max(100, 4k)`, query embedded with bge-small query prompt |
| hybrid | app-side **RRF** (k = 60) over BM25 and kNN windows (default 50) |
| hybrid_native | ES `retriever.rrf` with the same two retrievers |

**Filters** (`SessionFilters`: day, track, format, level, speaker, entity, time window, exclude,
content-only) become one `bool.filter` applied **inside both** the BM25 query and the kNN filter,
so semantic similarity can never surface a session outside the user's constraints.

Why app-side RRF by default: explanations show each result's BM25 and vector rank; the native
retriever cannot return per-retriever ranks. Rankings are identical (verified); native is faster
(one round trip). Facets are computed over the full ranked window.

Graceful degradation: no embeddings → BM25 with `degraded: ["vector_unavailable"]`; native RRF
error → app RRF with `degraded: ["native_rrf_unavailable"]`.

## Embedding calibration (measured 2026-11-09)
bge-small cosines are compressed: session↔session median 0.657, p90 0.747, p99 0.82;
on-topic queries reach top-1 0.76–0.83, off-topic ones 0.56–0.62. Hence assistant coverage
threshold 0.70, recommendation cosine rescale [0.60, 0.85], related-session rescale [0.70, 0.90],
"similar abstract" alternatives ≥ 0.82.

## Evaluation (`uv run kubecompass evaluate`)
12 representative attendee queries, 225 graded judgments (0/1/2) over a pool of the top-10 of every
method. **Judged by the AI assistant during development, not independent humans**; sessions outside
the pool count as non-relevant, which favors pooled methods. Treat as indicative.

| Method | P@5 | R@10 | nDCG@10 | mean latency |
|---|---|---|---|---|
| BM25 | 0.850 | 0.609 | 0.735 | 20 ms |
| Vector (kNN) | 0.883 | 0.615 | 0.708 | 38 ms |
| Hybrid, app RRF | 0.867 | 0.655 | 0.771 | 90 ms |
| Hybrid, native ES RRF | 0.867 | 0.655 | 0.771 | 44 ms |
| Hybrid + graph re-rank (PPR) | 0.850 | 0.660 | 0.796 | 79 ms |
| Personalized pipeline | 0.867 | 0.629 | 0.744 | 83 ms |

Personalized pipeline explanation coverage (top-10 with ≥1 grounded reason): 1.00.

Reading: hybrid beats either retriever alone on recall and nDCG. Graph re-ranking scores higher on
nDCG@10 here (+0.025), but with 12 queries this is within noise; we do **not** claim graph expansion
improves relevance in general. The personalized pipeline is optimized for a profile (it mixes in
exploratory picks and format/level preferences), so a query-relevance metric understates it. It
is not a regression signal. Latency includes embedding the query (local CPU).
