# Data provenance

| Origin | Meaning | Examples | UI label |
|---|---|---|---|
| `explicit` | Supplied directly by Sessionize | title, abstract, times, rooms, speakers, track, CNCF project tags, company | **Official** |
| `extracted` | Matched in source text by the vocabulary; the sentence is stored as evidence | session USES vLLM ("We run vLLM behind…") | **From text** |
| `curated` | From the maintained vocabulary hierarchy | vLLM PART_OF Model Serving | **Curated** |
| `inferred` | Computed by KubeCompass | co-occurrence, abstract similarity, maintainer→WORKS_ON | **Inferred** (dashed edges) |
| `ai_extracted` | Produced by an LLM (not used by default) | – | **AI-extracted** |
| `verified` | Confirmed externally (reserved) | – | **Verified** |

Every session/speaker record keeps: `source_system`, `source_id`, `source_url`, `ingested_at`,
`ingestion_version`, `payload_hash` (sha256 of the raw record). Raw payloads stay in `data/raw/`
and are never returned by the API. Snapshots (`data/processed/<conf>/dataset.json` + 5 history
versions), change logs and ingestion status are kept per conference.

**Rules**
- Missing source fields stay missing (no defaults that look like data).
- Inferred/extracted information is never shown or narrated as confirmed fact; the assistant's
  system prompt requires this and records carry origin labels.
- Format classification records how it was derived (`format_origin`).
- Recommendation explanations quote abstracts verbatim; generated text never describes a session.

**External services & data handling**
Sessionize public API (read-only); Hugging Face (one-time download of the open embedding model);
Anthropic / OpenAI only if their keys are set, and local Ollama if running: they receive the attendee's
query text and public conference records, never guest ids or agenda contents. With Ollama only, no
text leaves the machine. Embeddings are computed locally.
