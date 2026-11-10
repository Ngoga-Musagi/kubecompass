"""Centralized runtime configuration. All values come from env vars (prefix KUBECOMPASS_)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_ROOT = Path(__file__).resolve().parents[3]


def env_file_path() -> Path:
    """Active environment profile: KUBECOMPASS_ENV_FILE (e.g. .env.cloud) or the repo .env.

    Lets the same checkout switch between local Elasticsearch and Elastic Cloud.
    """
    chosen = os.environ.get("KUBECOMPASS_ENV_FILE")
    if not chosen:
        return _DEFAULT_ROOT / ".env"
    path = Path(chosen)
    return path if path.is_absolute() else _DEFAULT_ROOT / path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KUBECOMPASS_",
        env_file=None,  # loaded explicitly from the active profile in get_settings()
        extra="ignore",
    )

    repo_root: Path = _DEFAULT_ROOT
    data_root: Path | None = None  # default: <repo>/data (tests point this at a temp dir)
    default_conference_id: str = "kubecon-na-2026"

    # Elasticsearch
    es_url: str = "http://localhost:9200"
    es_api_key: SecretStr | None = None
    es_index_prefix: str = "conference"
    es_timeout_seconds: float = 10.0
    # Kibana (Elastic Cloud): needed for Agent Builder, Workflows and the "elastic" LLM provider.
    # The same API key is used for Elasticsearch and Kibana.
    kibana_url: str | None = None
    kibana_space: str | None = None  # None = default space

    # Elastic Agent Builder / Workflows
    elastic_agent_id: str = "kubecompass-guide"  # conversational agent with custom tools
    elastic_llm_agent_id: str = "kubecompass-llm"  # tool-less agent used as an LLM provider
    elastic_llm_connector_id: str | None = None  # None = the deployment's default LLM

    # Embeddings. fastembed = local ONNX (default). elastic = an Elasticsearch inference endpoint
    # such as the Jina models on the Elastic Inference Service (Elastic Cloud).
    embedding_provider: Literal["fastembed", "elastic", "none"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = 384
    elastic_embedding_inference_id: str = ".jina-embeddings-v3"
    # semantic_text field for Agent Builder / Workflows semantic queries; empty = disabled.
    semantic_text_inference_id: str = ""
    model_cache_dir: Path | None = None  # default: <repo>/.cache/fastembed

    # LLM (optional). Provider order as a comma list, e.g. "ollama" or "anthropic,ollama".
    # "auto" = anthropic → openai → ollama, using those with credentials / a running server.
    # Keys come from ANTHROPIC_API_KEY / OPENAI_API_KEY (no prefix) and never leave the server.
    llm_provider: str = "auto"
    anthropic_model: str = Field(
        default="claude-opus-5-5",
        validation_alias=AliasChoices("KUBECOMPASS_ANTHROPIC_MODEL", "KUBECOMPASS_LLM_MODEL"),
    )
    openai_model: str = "gpt-5.4-mini"
    openai_base_url: str | None = None  # None = api.openai.com
    openai_reasoning_effort: str | None = "low"  # GPT-5 family; set "" for non-reasoning models
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3.5:4b-q4_K_M"
    ollama_reasoning_effort: str | None = "none"  # Qwen 3.5 thinks for minutes otherwise
    ollama_timeout_seconds: float = 120.0
    llm_timeout_seconds: float = 60.0
    # Public deployments: cap paid LLM calls per UTC day across all visitors (0 = unlimited).
    # When reached, the app falls back to rule-based parsing / retrieval-only answers.
    llm_daily_call_limit: int = 0

    # Search
    fusion_mode: Literal["app", "native"] = "app"
    rrf_rank_constant: int = 60
    retrieval_window: int = 50

    # Admin / safety
    admin_token: SecretStr | None = Field(
        default=None, description="Bearer token required for /api/admin/*. Unset = admin disabled."
    )
    identity_secret: SecretStr | None = Field(
        default=None,
        description="Server secret that turns an email/username into a personal attendee id "
        "(HMAC). Keep it stable: changing it detaches everyone from their saved data.",
    )
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    rate_limit_per_minute: int = 30
    allow_remote_refresh: bool = True

    @property
    def data_dir(self) -> Path:
        return self.data_root or self.repo_root / "data"

    @property
    def resolved_model_cache_dir(self) -> Path:
        return self.model_cache_dir or self.repo_root / ".cache" / "fastembed"

    @property
    def conferences_dir(self) -> Path:
        return self.repo_root / "deployment" / "configuration" / "conferences"

    @property
    def vocabulary_path(self) -> Path:
        return self.repo_root / "deployment" / "configuration" / "vocabulary" / "cloud-native.yaml"

    @property
    def ranking_path(self) -> Path:
        return self.repo_root / "deployment" / "configuration" / "ranking.yaml"


@lru_cache
def get_settings() -> Settings:
    # Export repo-root .env into the process environment (real env vars win) so non-prefixed
    # provider credentials such as ANTHROPIC_API_KEY reach their SDKs in local development.
    path = env_file_path()
    load_dotenv(path, override=False)
    return Settings(_env_file=path if path.exists() else None)  # type: ignore[call-arg]
