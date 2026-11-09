"""Deploy KubeCompass as a public Hugging Face Docker Space (Docker Spaces require HF PRO).

    uv run --with huggingface_hub python scripts/deploy_hf_space.py --space <user>/kubecompass \
        --env-file .env [--dry-run] [--private]

Requires `HF_TOKEN` (a write token from https://huggingface.co/settings/tokens) in the environment
or a prior `hf auth login`. Data stays in Elastic Cloud; the Space runs the stateless app.

Secrets (endpoints + keys) are stored as encrypted Space *secrets*, never in files or variables
(Space variables are publicly visible). Values are never printed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / ".cache" / "hf-space"

# Copied into the Space repo (paths relative to the repo root).
INCLUDE = [
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/app",
    "frontend",
    "deployment/configuration",
    "deployment/docker/app-start.sh",
    "elasticsearch",
    "data/raw",
]
IGNORE = shutil.ignore_patterns(
    "node_modules",
    ".next",
    "__pycache__",
    "*.pyc",
    "test-results",
    "playwright-report",
    "tests",
    ".env*",
    "*.tsbuildinfo",
)

SECRET_NAMES = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "KUBECOMPASS_ES_URL",
    "KUBECOMPASS_ES_API_KEY",
    "KUBECOMPASS_KIBANA_URL",
]
SETTING_NAMES = [
    "KUBECOMPASS_EMBEDDING_PROVIDER",
    "KUBECOMPASS_ELASTIC_EMBEDDING_INFERENCE_ID",
    "KUBECOMPASS_EMBEDDING_DIMENSIONS",
    "KUBECOMPASS_SEMANTIC_TEXT_INFERENCE_ID",
    "KUBECOMPASS_LLM_PROVIDER",
    "KUBECOMPASS_OPENAI_MODEL",
]
# Public-safety defaults (override with --set NAME=VALUE).
PUBLIC_DEFAULTS = {
    "KUBECOMPASS_LLM_PROVIDER": "openai",  # no local Ollama on a host; keep cost predictable
    "KUBECOMPASS_LLM_DAILY_CALL_LIMIT": "300",
    "KUBECOMPASS_RATE_LIMIT_PER_MINUTE": "10",
}

README = """---
title: KubeCompass
emoji: 🧭
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: AI-native discovery for KubeCon + CloudNativeCon NA 2026
---

# KubeCompass

Tell KubeCompass what you want to learn at KubeCon + CloudNativeCon North America 2026: it finds the
sessions, speakers and technologies that matter, explains why with evidence from the official
schedule, and helps you plan a conflict-free agenda (.ics export).

Built on Elastic Cloud Serverless (BM25 + Jina vector hybrid search, knowledge graph, Agent Builder,
Workflows). Guest mode: your agenda is tied to an anonymous ID in your browser.
Saving a session does not reserve a seat.
"""


def stage() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    for rel in INCLUDE:
        src, dst = ROOT / rel, STAGE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=IGNORE)
        else:
            shutil.copy2(src, dst)
    shutil.copy2(ROOT / "deployment" / "docker" / "app.Dockerfile", STAGE / "Dockerfile")
    (STAGE / "README.md").write_text(README, encoding="utf-8")
    leaked = [p for p in STAGE.rglob(".env*") if p.name not in (".env.example",)]
    if leaked:
        sys.exit(f"Refusing to deploy: env files staged: {leaked}")


def read_env(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    return {k: v for k, v in dotenv_values(path).items() if v}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--space",
        default=None,
        help="<user-or-org>/<space-name> (default: <your HF user>/kubecompass)",
    )
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--private", action="store_true", help="Create the Space as private")
    ap.add_argument("--set", action="append", default=[], help="Override a setting NAME=VALUE")
    ap.add_argument("--dry-run", action="store_true", help="Only build the staging folder")
    args = ap.parse_args()

    stage()
    env = read_env(ROOT / args.env_file)
    shared = ROOT / ".env"  # HF_TOKEN's single source when profile files (.env.cloud) omit it
    token = (
        os.environ.get("HF_TOKEN")
        or env.get("HF_TOKEN")
        or (read_env(shared).get("HF_TOKEN") if shared.exists() else None)
    )
    if args.space is None:
        if not token:
            print("ERROR: pass --space or provide HF_TOKEN")
            return 1
        from huggingface_hub import HfApi

        args.space = f"{HfApi(token=token).whoami()['name']}/kubecompass"
    print(f"Space: {args.space}")
    settings = {k: env[k] for k in SETTING_NAMES if k in env}
    settings.update(PUBLIC_DEFAULTS)
    for item in args.set:
        k, _, v = item.partition("=")
        settings[k] = v
    # Only ship credentials the public LLM chain actually uses (least exposure).
    chain = {p.strip() for p in settings.get("KUBECOMPASS_LLM_PROVIDER", "").split(",")}
    needed = {"KUBECOMPASS_ES_URL", "KUBECOMPASS_ES_API_KEY"}
    if "openai" in chain:
        needed.add("OPENAI_API_KEY")
    if "anthropic" in chain:
        needed.add("ANTHROPIC_API_KEY")
    if "elastic" in chain:
        needed.add("KUBECOMPASS_KIBANA_URL")
    secrets = {k: env[k] for k in SECRET_NAMES if k in env and k in needed}
    print(f"Staged {sum(1 for p in STAGE.rglob('*') if p.is_file())} files in {STAGE}")
    print("Secrets to set:", ", ".join(secrets) or "(none)")
    print("Settings:", ", ".join(f"{k}={v}" for k, v in settings.items()))
    missing = [k for k in ("KUBECOMPASS_ES_URL", "KUBECOMPASS_ES_API_KEY") if k not in secrets]
    if missing:
        print("ERROR: missing in env file:", ", ".join(missing))
        return 1
    if args.dry_run:
        print("Dry run: nothing uploaded.")
        return 0

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(
        args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True
    )
    for k, v in secrets.items():
        api.add_space_secret(args.space, k, v)
    for k, v in settings.items():  # settings are non-sensitive; stored as secrets too to keep
        api.add_space_secret(args.space, k, v)  # the public Space page clean
    api.upload_folder(
        repo_id=args.space,
        repo_type="space",
        folder_path=str(STAGE),
        commit_message="Deploy KubeCompass",
    )
    print(f"Deployed. Build logs: https://huggingface.co/spaces/{args.space}")
    print(f"App URL (after build): https://{args.space.replace('/', '-').lower()}.hf.space")
    return 0


if __name__ == "__main__":
    sys.exit(main())
