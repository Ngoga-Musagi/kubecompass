# Public deployment

KubeCompass's data, search, agent and workflows live in **Elastic Cloud**. Only the stateless app
(Next.js UI + FastAPI) needs hosting. It ships as **one container** (`deployment/docker/app.Dockerfile`):
the UI listens on `$PORT` (default 7860) and proxies `/api/*` to the API inside the container, so
there is one public URL and no CORS. Measured: ~240 MB RAM, all browser journeys pass against it.


## Where to host (checked 2026-11-09)

| Option | Cost | Fit | Caveats |
|---|---|---|---|
| **Google Cloud Run** (recommended) | Free monthly allowance (~2M requests, 180k vCPU-s, 360k GiB-s); needs a GCP account with billing enabled | Full vCPU per instance, scales to zero, HTTPS URL, Secret Manager | Cold start after idle (~10–20 s); set a budget alert |
| Hugging Face Spaces (Docker) | **Requires HF PRO** (Docker/Gradio Spaces on free CPU need PRO; only static Spaces are free) | Easiest: `scripts/deploy_hf_space.py` does everything | Paid subscription |
| Render (web service) | Free instance: 512 MB, 0.1 CPU, sleeps after 15 min idle | Deploys from a GitHub repo with the Dockerfile | 0.1 CPU is slow for Next.js + Python; ~1 min wake-up; may need a card |
| Koyeb | One free instance (512 MB, 0.1 vCPU) | Docker image or GitHub | Same CPU limits; free-tier status reportedly changing |
| Vercel (UI) + one of the above (API) | Vercel Hobby is free | Best Next.js hosting | Two services: build the UI with `NEXT_PUBLIC_API_URL=<api url>`, add it to `KUBECOMPASS_CORS_ORIGINS` |

Free tiers change often; confirm on each provider's pricing page.

## Recommended: Google Cloud Run
Prerequisites: a Google Cloud project with billing enabled, the [gcloud CLI](https://cloud.google.com/sdk/docs/install)
(`winget install Google.CloudSDK`), then `gcloud auth login` and `gcloud config set project <PROJECT_ID>`.

```bash
REGION=us-central1            # same region family as the Elastic project keeps latency low
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create kubecompass --repository-format=docker --location=$REGION
gcloud auth configure-docker $REGION-docker.pkg.dev

IMAGE=$REGION-docker.pkg.dev/$(gcloud config get-value project)/kubecompass/app:latest
docker build -f deployment/docker/app.Dockerfile -t $IMAGE . && docker push $IMAGE

# Secrets (enter values when prompted; never put them on the command line history)
for s in kc-es-url kc-es-api-key kc-openai-key; do gcloud secrets create $s --data-file=- ; done

gcloud run deploy kubecompass --image $IMAGE --region $REGION --allow-unauthenticated \
  --port 7860 --memory 1Gi --cpu 1 --min-instances 0 --max-instances 2 \
  --set-secrets KUBECOMPASS_ES_URL=kc-es-url:latest,KUBECOMPASS_ES_API_KEY=kc-es-api-key:latest,OPENAI_API_KEY=kc-openai-key:latest \
  --set-env-vars KUBECOMPASS_EMBEDDING_PROVIDER=elastic,KUBECOMPASS_ELASTIC_EMBEDDING_INFERENCE_ID=.jina-embeddings-v3,KUBECOMPASS_EMBEDDING_DIMENSIONS=1024,KUBECOMPASS_SEMANTIC_TEXT_INFERENCE_ID=.jina-embeddings-v3,KUBECOMPASS_LLM_PROVIDER=openai,KUBECOMPASS_LLM_DAILY_CALL_LIMIT=300,KUBECOMPASS_RATE_LIMIT_PER_MINUTE=10
```
The command prints the public `https://kubecompass-….run.app` URL. `--max-instances 2` bounds cost;
the daily AI cap is per instance.

## Least-privilege Elastic key (recommended for any public host)
Elasticsearch does not let an API key create another key with privileges, so create it in Kibana while
logged in as yourself: **Project settings → API keys → Create API key → enable "Control security
privileges"** and paste [`elasticsearch/security/kubecompass-public-app-role.json`](../elasticsearch/security/kubecompass-public-app-role.json)
(read conference data, write only attendee agendas, call Jina; no ingest, delete or Kibana access).
Use that key as the host's `KUBECOMPASS_ES_API_KEY`; keep your admin key local for ingestion/setup.
If the Kibana dialog only offers other key types (e.g. an MCP-client key), use the Dev Tools console
in Kibana (also as yourself) instead:
```
POST /_security/api_key
{ "name": "kubecompass-public", "expiration": "90d", "role_descriptors": <paste the JSON file> }
```
and copy the `encoded` value from the response.

## Hugging Face Space (needs PRO)
```bash
uv run --project backend --with huggingface_hub python scripts/deploy_hf_space.py --env-file .env.deploy --dry-run
uv run --project backend --with huggingface_hub python scripts/deploy_hf_space.py --env-file .env.deploy
```
`HF_TOKEN` is read from the env file; the Space name defaults to `<your HF user>/kubecompass`.

## Other hosts (same image)
```bash
docker build -f deployment/docker/app.Dockerfile -t kubecompass-app .
```
Set these environment variables/secrets on the host (individually, not via an env file containing
inline comments): `KUBECOMPASS_ES_URL`, `KUBECOMPASS_ES_API_KEY`, `KUBECOMPASS_EMBEDDING_PROVIDER=elastic`,
`KUBECOMPASS_ELASTIC_EMBEDDING_INFERENCE_ID=.jina-embeddings-v3`, `KUBECOMPASS_EMBEDDING_DIMENSIONS=1024`,
`KUBECOMPASS_SEMANTIC_TEXT_INFERENCE_ID=.jina-embeddings-v3`, `OPENAI_API_KEY`,
`KUBECOMPASS_LLM_PROVIDER=openai`, `KUBECOMPASS_LLM_DAILY_CALL_LIMIT=300`,
`KUBECOMPASS_RATE_LIMIT_PER_MINUTE=10`. The container listens on `$PORT` (hosts like Cloud Run and
Render set it automatically).

## Public-access checklist
- [ ] Least-privilege Elastic key for the app; admin key only on your machine.
- [ ] OpenAI budget/usage limit set; daily AI cap configured.
- [ ] `KUBECOMPASS_ADMIN_TOKEN` unset (admin API disabled) unless you need remote refresh.
- [ ] No `.env` files in the image (enforced by `.dockerignore` and the deploy script).
- [ ] Guest mode only: agendas are tied to an anonymous browser ID; no personal data is collected.
- [ ] Rotate keys if a Space is ever made private→public by mistake or a key leaks.
