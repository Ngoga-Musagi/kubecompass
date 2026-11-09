# KubeCompass developer commands. Windows: run from Git Bash (make via `winget install GnuWin32.Make`)
# or use the underlying commands shown here.
CLOUD := KUBECOMPASS_ENV_FILE=.env.cloud

.PHONY: help up down es install ingest refresh status dev-backend dev-frontend test test-unit \n        app-image deploy-dry cloud-check cloud-ingest cloud-setup cloud-teardown cloud-api cloud-up sim-up sim-setup sim-down \
        test-integration test-frontend test-e2e lint typecheck evaluate screenshots clean

help:            ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-18s %s\n",$$1,$$2}'

up:              ## Full stack in Docker (ES + backend + frontend)
	docker compose up -d --build

down:            ## Stop the Docker stack
	docker compose down

es:              ## Start only Elasticsearch (local dev)
	docker compose up -d elasticsearch

install:         ## Install backend + frontend dependencies
	cd backend && uv sync
	cd frontend && npm ci

ingest:          ## Ingest local Sessionize files into Elasticsearch
	cd backend && uv run kubecompass ingest

refresh:         ## Fetch live Sessionize endpoints and safely refresh
	cd backend && uv run kubecompass ingest --remote

status:          ## Show last ingestion status / data freshness
	cd backend && uv run kubecompass status

dev-backend:     ## API on :8000
	cd backend && uv run uvicorn app.main:app --port 8000

dev-frontend:    ## UI on :3000
	cd frontend && npm run dev

test: test-unit test-integration test-frontend  ## All automated tests (needs ES)

test-unit:       ## Backend unit tests (no services needed)
	cd backend && uv run pytest tests/unit -q

test-integration: ## Backend end-to-end on real data (needs ES)
	cd backend && uv run pytest tests/integration -q -p no:logging

test-frontend:   ## Frontend unit tests
	cd frontend && npm test

test-e2e:        ## Browser journey (needs running stack + ingested data)
	cd frontend && npx playwright test

lint:            ## Lint backend + frontend
	cd backend && uv run ruff check app tests
	cd frontend && npm run lint

typecheck:       ## mypy + tsc
	cd backend && uv run mypy app
	cd frontend && npm run typecheck

evaluate:        ## Search/recommendation evaluation → data/evaluation/results.json
	cd backend && uv run kubecompass evaluate

screenshots:     ## Visual audit screenshots → .cache/screens
	cd frontend && MSYS_NO_PATHCONV=1 node scripts/screenshot.mjs / /recommendations /graph /agenda /assistant /speakers

clean:           ## Remove caches (keeps raw data)
	rm -rf .cache frontend/.next frontend/test-results backend/.pytest_cache

# ---- Elastic Cloud (profile: .env.cloud; see docs/ELASTIC_CLOUD.md) ----------------------------
cloud-check:     ## Verify Elastic Cloud connection, Jina endpoint, Agent Builder, Workflows
	cd backend && $(CLOUD) uv run kubecompass elastic check

cloud-ingest:    ## Ingest data into Elastic Cloud (Jina embeddings)
	cd backend && $(CLOUD) uv run kubecompass ingest

cloud-setup:     ## Create/update Agent Builder tools + agents and Workflows
	cd backend && $(CLOUD) uv run kubecompass elastic setup

cloud-teardown:  ## Remove KubeCompass tools, agents and workflows from Kibana
	cd backend && $(CLOUD) uv run kubecompass elastic teardown

cloud-api:       ## API on :8000 against Elastic Cloud
	cd backend && $(CLOUD) uv run uvicorn app.main:app --port 8000

cloud-up:        ## Docker app (backend + frontend) against Elastic Cloud
	$(CLOUD) docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d --build backend frontend

# ---- Local Elastic Cloud simulator (secured ES + Kibana) for Agent Builder / Workflows -------
SIM := docker compose -f deployment/docker/elastic-cloud-sim.compose.yml

sim-up:          ## Start secured ES :9201 + Kibana :5602 and write .cache/env.sim
	$(SIM) up -d
	@until curl -s -u elastic:kubecompass-sim localhost:9201 >/dev/null; do sleep 3; done
	@KEY=$$(curl -s -u elastic:kubecompass-sim -H "Content-Type: application/json" -X POST localhost:9201/_security/api_key -d '{"name":"kubecompass-sim"}' | python -c "import json,sys;print(json.load(sys.stdin)['encoded'])"); 	printf "KUBECOMPASS_ES_URL=http://localhost:9201
KUBECOMPASS_ES_API_KEY=%s
KUBECOMPASS_KIBANA_URL=http://localhost:5602
KUBECOMPASS_EMBEDDING_PROVIDER=fastembed
KUBECOMPASS_DATA_ROOT=$(CURDIR)/.cache/sim-data
" "$$KEY" > .cache/env.sim
	@echo "Simulator ready; profile .cache/env.sim (Kibana may need ~1 min more)"

sim-setup:       ## Ingest data + provision tools/agents/workflows into the simulator
	cd backend && KUBECOMPASS_ENV_FILE=.cache/env.sim uv run kubecompass ingest
	cd backend && KUBECOMPASS_ENV_FILE=.cache/env.sim uv run kubecompass elastic setup

sim-down:        ## Stop and remove the simulator (and its data)
	$(SIM) down -v

# ---- Public deployment (docs/DEPLOYMENT.md) ---------------------------------------------------
app-image:       ## Build the single-container public image (UI + API)
	docker build -f deployment/docker/app.Dockerfile -t kubecompass-app .

deploy-dry:      ## Preview a Hugging Face Space deploy (SPACE=user/kubecompass ENV=.env.deploy)
	uv run --project backend --with huggingface_hub python scripts/deploy_hf_space.py --space $(SPACE) --env-file $(or $(ENV),.env.deploy) --dry-run
