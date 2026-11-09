# Running KubeCompass on Elastic Cloud Serverless

Local Elasticsearch (Docker) remains the default for experimentation. Elastic Cloud is a separate
**profile**: same code, selected with `KUBECOMPASS_ENV_FILE=.env.cloud` (the `make cloud-*` targets
set it for you). Local and cloud data are independent; each needs its own `ingest`.

| Hackathon requirement | How KubeCompass uses it |
|---|---|
| Elastic Cloud Serverless | All indices (sessions, speakers, entities, relationships, attendees, changes) live in the Serverless project; versioned indices + alias swaps; Serverless-safe settings and health checks |
| Ingest your data | `make cloud-ingest`: official Sessionize data → validated, normalized, graph-extracted → bulk-indexed |
| Jina models for embeddings | `.jina-embeddings-v3` on the Elastic Inference Service: 1024-d vectors for the app's kNN/hybrid search **and** a native `semantic_text` field (`semantic_content`) for Agent Builder / Workflows |
| Agent Builder + custom tools | Agent `kubecompass-guide` with 7 custom tools (2 index-search, 4 ES\|QL, 1 workflow) + `platform.core.search`; plus a tool-less `kubecompass-llm` agent the app uses as its LLM |
| Elastic Workflows | Daily briefing (07:00 America/Denver), hourly schedule-change watch, on-demand topic briefing (exposed to the agent as a tool); outputs stored in `kubecompass-briefings` |

Definitions are version-controlled: `elasticsearch/agent-builder/{tools,agents}/*.json` and
`elasticsearch/workflows/*.yaml`; `kubecompass elastic setup` creates or updates them (idempotent).

## 1. Create the project (once)
1. Sign up at https://ela.st/hack-kubecon and create an **Elasticsearch Serverless** project.
2. From the project page copy the **Elasticsearch endpoint** and the **Kibana URL**.
3. Create an **API key** (Project settings → API keys; give it access to `conference*`,
   `kubecompass-*` and Kibana features) and copy the encoded value.
4. In Kibana, open **Workflows**; if it isn't visible, enable the advanced setting
   *Elastic Workflows* (`workflows:ui:enabled`) in Stack Management → Advanced settings.

## 2. Configure the cloud profile
```bash
cp .env.cloud.example .env.cloud   # fill in KUBECOMPASS_ES_URL, KUBECOMPASS_ES_API_KEY, KUBECOMPASS_KIBANA_URL
make cloud-check                   # or: cd backend && KUBECOMPASS_ENV_FILE=.env.cloud uv run kubecompass elastic check
```
`cloud-check` verifies: Elasticsearch (should report flavor `serverless`), the `.jina-embeddings-v3`
inference endpoint, and Agent Builder / Workflows APIs. If Jina is not listed, either pick another
inference endpoint id shown in Kibana (Dev Tools: `GET _inference/_all`) or fall back to local
embeddings (`KUBECOMPASS_EMBEDDING_PROVIDER=fastembed`, `KUBECOMPASS_EMBEDDING_DIMENSIONS=384`,
empty `KUBECOMPASS_SEMANTIC_TEXT_INFERENCE_ID`).

`.env.cloud` is git-ignored. LLM keys can go there too; local Ollama keeps working from your machine.

## 3. Ingest the data into the cloud (Jina embeddings)
```bash
make cloud-ingest            # local data/raw files → cloud
# or live Sessionize:  cd backend && KUBECOMPASS_ENV_FILE=.env.cloud uv run kubecompass ingest --remote
```
Embeddings are computed by Jina in Elastic (first run: ~1,300 texts in batches of 32). Refreshes are
safe exactly as locally: new versioned indices, alias swap only after success.

## 4. Create the agent, tools and workflows
```bash
make cloud-setup             # kubecompass elastic setup  (add --skip-workflows if Workflows is off)
```
Order: workflows → tools → agents. Re-running updates in place. If a workflow fails, the workflow tool
is skipped and the agent is still created without it. Remove everything with `make cloud-teardown`.

Try it in Kibana → Agents → **KubeCompass Guide**: "Which sessions on 2026-11-11 cover GPU scheduling?",
"How is vLLM connected to other topics?", "Prepare a briefing on eBPF networking" (runs the workflow).
Workflows → *KubeCompass daily briefing* → Run; results appear in the `kubecompass-briefings` index.

## 5. Run the app against the cloud
```bash
make cloud-api                       # API on :8000 using the cloud profile
cd frontend && npm run dev           # unchanged; talks to the API
# or everything in Docker:  make cloud-up
```
`GET /api/health` shows `elasticsearch: ok`, the embedding model `elastic:.jina-embeddings-v3`, and the
LLM chain. With `KUBECOMPASS_LLM_PROVIDER=auto` the chain is Anthropic → OpenAI → **Elastic Agent
Builder** (`kubecompass-llm`, the project's default LLM, no extra key) → Ollama.

## Switching back to local
Run the normal commands without `KUBECOMPASS_ENV_FILE` (`make ingest`, `make dev-backend`): local Docker
Elasticsearch, FastEmbed 384-d, your `.env`.

## Test locally first: the Elastic Cloud simulator
A secured Elasticsearch + Kibana 9.4.8 (trial license, API keys) that behaves like a cloud project for
Agent Builder and Workflows; no Elastic Inference Service, so it uses FastEmbed embeddings.
```bash
make sim-up        # ES :9201, Kibana :5602 (user elastic / kubecompass-sim), writes .cache/env.sim
make sim-setup     # ingest + kubecompass elastic setup against the simulator
make sim-down
```
To chat with the agent in the simulator, add an LLM connector in Kibana (e.g. OpenAI-compatible →
`http://host.docker.internal:11434/v1/chat/completions`, model `qwen3-vl:4b-instruct` for reliable
tool calls), or pass `connector_id` to the converse API.

Verified in the simulator (2026-11-09): all 7 tools, 2 agents and 3 workflows provision and update
idempotently; every ES|QL tool returns real results; the agent selects the right custom tools; the agent
runs the briefing workflow through its workflow tool; all three workflows complete and write to
`kubecompass-briefings`; the app's `elastic` LLM provider works for intent parsing and the assistant.

Findings baked into the definitions and their tests:
- ES|QL tool param types must be `string|integer|float|boolean|date|array`.
- The workflow validator rejects YAML booleans inside `term` queries (use `"true"`) and `rrule` with
  `freq: HOURLY` (use `every: "1h"`). A rejected workflow still saves but shows `valid: false`.
- `{{ now }}` renders a JavaScript date string; use `{{ "now" | date: "%Y-%m-%dT%H:%M:%SZ" }}`.
- `ai.agent` output is `{ message }`; index-search tools need an LLM (the project default on Cloud).
- Workflow tools use `{"type": "workflow", "configuration": {"workflow_id": ...}}`.

## Notes and limits
- `semantic_text` with Jina runs inference at ingest; the app's own `embedding` field uses the same model
  through the `_inference` API so app search and Agent Builder search agree.
- Elastic Inference Service availability and rate limits depend on your project's region.
- Not yet run against a real Serverless project (needs your credentials); EIS/Jina is cloud-only, so
  the Jina code path is covered by unit tests, not the simulator.
