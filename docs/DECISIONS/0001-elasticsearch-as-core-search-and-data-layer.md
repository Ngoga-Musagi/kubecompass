# 0001 Elasticsearch as the core search and indexed-data layer

Status: accepted (2026-11-09)

**Context.** The product is search-centric (keyword, semantic, hybrid, facets, autocomplete) and
must also hold relationships and attendee state. The hackathon track is Elasticsearch.

**Decision.** Elasticsearch 9.4.8 stores sessions, speakers, entities, relationships, attendee
state and change logs. Vectors use `dense_vector` (HNSW, cosine) next to BM25 fields; filters,
aggregations, `search_as_you_type`, synonyms and the `rrf` retriever are used natively. The API
reads conference data only from ES; on-disk snapshots exist for safe refresh and audit.

**Consequences.** One data store to operate. Attendee state in ES is fine for a guest-mode demo;
a relational store would be preferable for accounts at scale.
