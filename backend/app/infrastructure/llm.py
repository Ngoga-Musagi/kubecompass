"""LLM providers (optional): Anthropic, OpenAI, and local models via Ollama.

The product is fully usable without an LLM: intent parsing falls back to the
vocabulary-based parser and the assistant falls back to extractive answers.
Only the attendee's own query text and retrieved *public* conference records
are sent to a provider; agenda contents and guest ids are never sent.

Providers are combined in a `ChainLLMProvider` (configured order, e.g.
"anthropic,openai,ollama"): a request goes to the first healthy provider and
falls through on failure. A provider failing for a permanent reason (bad key,
no credits, unknown model) is skipped for a cool-down period.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

import anthropic
import httpx
import openai
from pydantic import BaseModel

from app.config.settings import Settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

PERMANENT_COOLDOWN_S = 600.0  # bad credentials, no credits, unknown model
TRANSIENT_COOLDOWN_S = 30.0  # rate limits, timeouts, 5xx, unreachable


class LLMUnavailableError(RuntimeError):
    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


@dataclass(frozen=True)
class LLMText:
    text: str
    served_by: str  # "provider:model", shown to users for transparency


class LLMProvider(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def describe(self) -> str: ...

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMText: ...

    def structured(self, system: str, user: str, schema: type[T]) -> T: ...


class NullLLMProvider:
    name = "none"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    def describe(self) -> str:
        return f"not configured ({self.reason}); fallbacks active"

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMText:
        raise LLMUnavailableError(self.reason, permanent=True)

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        raise LLMUnavailableError(self.reason, permanent=True)


# ---- Anthropic -------------------------------------------------------------------------
class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, timeout: float) -> None:
        # Credentials resolve from ANTHROPIC_API_KEY / ant profile; never hardcoded.
        self._client = anthropic.Anthropic(timeout=timeout, max_retries=1)
        self.model = model

    @property
    def available(self) -> bool:
        return True

    def describe(self) -> str:
        return f"anthropic:{self.model}"

    def _wrap(self, exc: Exception) -> LLMUnavailableError:
        if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
            return LLMUnavailableError("Anthropic credentials rejected", permanent=True)
        if isinstance(exc, anthropic.NotFoundError):
            return LLMUnavailableError(f"Anthropic model {self.model} not found", permanent=True)
        if isinstance(exc, anthropic.RateLimitError):
            return LLMUnavailableError("Anthropic rate limited")
        if isinstance(exc, anthropic.APIStatusError):
            if "credit balance" in str(exc).lower():
                return LLMUnavailableError(
                    "Anthropic account has insufficient API credits", permanent=True
                )
            return LLMUnavailableError(f"Anthropic error ({exc.status_code})")
        if isinstance(exc, anthropic.APIConnectionError):
            return LLMUnavailableError("Anthropic unreachable")
        return LLMUnavailableError(f"Anthropic call failed: {type(exc).__name__}")

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMText:
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as exc:
            raise self._wrap(exc) from exc
        if response.stop_reason == "refusal":
            raise LLMUnavailableError("Anthropic declined the request")
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            raise LLMUnavailableError("Anthropic returned an empty answer")
        return LLMText(text, f"anthropic:{response.model}")

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low"},
                output_format=schema,
            )
        except anthropic.APIError as exc:
            raise self._wrap(exc) from exc
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise LLMUnavailableError("Anthropic returned no structured output")
        return response.parsed_output


# ---- OpenAI-compatible (OpenAI API, Ollama, LM Studio, vLLM, …) --------------------------
class OpenAICompatibleProvider:
    """Chat Completions provider. Serves OpenAI and any OpenAI-compatible local server.

    `reasoning_effort` is only sent when configured: local reasoning models (e.g. Qwen 3.5 in
    Ollama) need "none" to answer quickly; many non-reasoning OpenAI models reject the field.
    """

    def __init__(
        self,
        name: str,
        model: str,
        base_url: str | None,
        api_key: str,
        timeout: float,
        reasoning_effort: str | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url
        self.reasoning_effort = reasoning_effort
        self._client = openai.OpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=1
        )

    @property
    def available(self) -> bool:
        return True

    def describe(self) -> str:
        return f"{self.name}:{self.model}"

    def _effort(self) -> str | openai.Omit:
        return self.reasoning_effort or openai.omit

    def _wrap(self, exc: Exception) -> LLMUnavailableError:
        who = self.name.capitalize()
        if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
            return LLMUnavailableError(f"{who} credentials rejected", permanent=True)
        if isinstance(exc, openai.NotFoundError):
            return LLMUnavailableError(f"{who} model {self.model} not found", permanent=True)
        if isinstance(exc, openai.RateLimitError):
            if "insufficient_quota" in str(exc):
                return LLMUnavailableError(f"{who} account has insufficient quota", permanent=True)
            return LLMUnavailableError(f"{who} rate limited")
        if isinstance(exc, openai.APITimeoutError):
            return LLMUnavailableError(f"{who} timed out")
        if isinstance(exc, openai.APIConnectionError):
            return LLMUnavailableError(f"{who} unreachable")
        if isinstance(exc, openai.APIStatusError):
            return LLMUnavailableError(f"{who} error ({exc.status_code})")
        if isinstance(exc, openai.LengthFinishReasonError | openai.ContentFilterFinishReasonError):
            return LLMUnavailableError(f"{who} output incomplete ({type(exc).__name__})")
        return LLMUnavailableError(f"{who} call failed: {type(exc).__name__}")

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMText:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                reasoning_effort=self._effort(),  # type: ignore[arg-type]
                # OpenAI's newer models require max_completion_tokens; local servers use max_tokens.
                max_tokens=openai.omit if self.name == "openai" else max_tokens,
                max_completion_tokens=max_tokens if self.name == "openai" else openai.omit,
            )
        except openai.OpenAIError as exc:
            raise self._wrap(exc) from exc
        choice = response.choices[0] if response.choices else None
        text = (choice.message.content or "").strip() if choice else ""
        if not text:
            raise LLMUnavailableError(f"{self.name} returned an empty answer")
        return LLMText(text, f"{self.name}:{response.model or self.model}")

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        try:
            response = self._client.chat.completions.parse(
                model=self.model,
                response_format=schema,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                reasoning_effort=self._effort(),  # type: ignore[arg-type]
            )
        except openai.OpenAIError as exc:
            raise self._wrap(exc) from exc
        except ValueError as exc:  # pydantic validation of a malformed local-model reply
            raise LLMUnavailableError(f"{self.name} returned invalid structured output") from exc
        parsed = response.choices[0].message.parsed if response.choices else None
        if parsed is None:
            raise LLMUnavailableError(f"{self.name} returned no structured output")
        return parsed


# ---- Elastic Agent Builder (managed LLM on Elastic Cloud) ---------------------------------
class ElasticAgentProvider:
    """Uses an Agent Builder agent (tool-less `kubecompass-llm`) via the converse API as an LLM.

    On Elastic Cloud this runs on the deployment's default LLM (no extra key). Structured
    output is requested as JSON in the message and validated locally.
    """

    name = "elastic"

    def __init__(self, settings: Settings) -> None:
        from app.elastic.kibana import KibanaClient

        self.agent_id = settings.elastic_llm_agent_id
        self.connector_id = settings.elastic_llm_connector_id
        self._kb = KibanaClient(settings, timeout=settings.llm_timeout_seconds * 2)

    @property
    def available(self) -> bool:
        return True

    def describe(self) -> str:
        return f"elastic:{self.agent_id}"

    def _converse(self, text: str) -> str:
        from app.elastic.kibana import KibanaError

        body: dict[str, object] = {"agent_id": self.agent_id, "input": text}
        if self.connector_id:
            body["connector_id"] = self.connector_id
        try:
            resp = self._kb.request("POST", "/api/agent_builder/converse", body) or {}
        except KibanaError as exc:
            permanent = exc.status in (401, 403, 404)
            raise LLMUnavailableError(f"Elastic Agent Builder: {exc}", permanent=permanent) from exc
        message = ((resp.get("response") or {}).get("message") or "").strip()
        if not message:
            raise LLMUnavailableError("Elastic Agent Builder returned an empty answer")
        return message

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMText:
        return LLMText(self._converse("\n\n".join([system, user])), self.describe())

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        import json as _json

        instruction = "Reply with ONLY a JSON object matching this JSON schema:"
        text = self._converse(
            "\n\n".join([system, user, instruction, _json.dumps(schema.model_json_schema())])
        )
        start, end = text.find("{"), text.rfind("}")
        try:
            return schema.model_validate_json(text[start : end + 1])
        except ValueError as exc:
            raise LLMUnavailableError("Elastic agent returned invalid structured output") from exc


# ---- Chain -----------------------------------------------------------------------------------
class ChainLLMProvider:
    name = "chain"

    def __init__(self, providers: list[LLMProvider]) -> None:
        self.providers = providers
        self._cooldown: dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.providers)

    def describe(self) -> str:
        now = time.monotonic()
        parts = []
        for p in self.providers:
            until = self._cooldown.get(p.describe(), 0)
            parts.append(p.describe() + (" (paused after errors)" if until > now else ""))
        return " → ".join(parts)

    def _candidates(self) -> list[LLMProvider]:
        now = time.monotonic()
        ready = [p for p in self.providers if self._cooldown.get(p.describe(), 0) <= now]
        return ready or self.providers  # if all are paused, try them anyway

    def _fail(self, p: LLMProvider, exc: LLMUnavailableError) -> None:
        delay = PERMANENT_COOLDOWN_S if exc.permanent else TRANSIENT_COOLDOWN_S
        with self._lock:
            self._cooldown[p.describe()] = time.monotonic() + delay
        log.warning("LLM provider %s failed (%s); falling through", p.describe(), exc)

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMText:
        errors: list[str] = []
        for p in self._candidates():
            try:
                return p.complete(system, user, max_tokens=max_tokens)
            except LLMUnavailableError as exc:
                self._fail(p, exc)
                errors.append(str(exc))
        raise LLMUnavailableError("; ".join(errors) or "no LLM providers")

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        errors: list[str] = []
        for p in self._candidates():
            try:
                return p.structured(system, user, schema)
            except LLMUnavailableError as exc:
                self._fail(p, exc)
                errors.append(str(exc))
        raise LLMUnavailableError("; ".join(errors) or "no LLM providers")


# ---- Budget guard ------------------------------------------------------------------------------
class BudgetedLLMProvider:
    """Caps LLM calls per UTC day (public demos). Over budget = LLM unavailable -> fallbacks."""

    def __init__(self, inner: LLMProvider, daily_limit: int) -> None:
        self.inner = inner
        self.name = inner.name
        self.daily_limit = daily_limit
        self._day = ""
        self._count = 0
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.inner.available

    def _spend(self) -> None:
        from datetime import UTC, datetime

        today = datetime.now(UTC).date().isoformat()
        with self._lock:
            if today != self._day:
                self._day, self._count = today, 0
            if self._count >= self.daily_limit:
                raise LLMUnavailableError("daily AI budget reached; using non-AI fallbacks")
            self._count += 1

    def describe(self) -> str:
        return f"{self.inner.describe()} (budget {self._count}/{self.daily_limit} today)"

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMText:
        self._spend()
        return self.inner.complete(system, user, max_tokens=max_tokens)

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        self._spend()
        return self.inner.structured(system, user, schema)


# ---- Factory ---------------------------------------------------------------------------------
def _ollama_reachable(base_url: str) -> bool:
    try:
        return httpx.get(f"{base_url.rstrip('/')}/models", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        return False


def build_llm_provider(settings: Settings) -> LLMProvider:
    wanted = [p.strip().lower() for p in settings.llm_provider.split(",") if p.strip()]
    if wanted in (["none"], []):
        return NullLLMProvider("LLM disabled by configuration")
    auto = wanted == ["auto"]
    order = ["anthropic", "openai", "elastic", "ollama"] if auto else wanted
    providers: list[LLMProvider] = []
    skipped: list[str] = []
    for name in order:
        if name == "anthropic":
            if any(
                os.environ.get(k)
                for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE")
            ):
                providers.append(
                    AnthropicProvider(settings.anthropic_model, settings.llm_timeout_seconds)
                )
            else:
                skipped.append("anthropic (no ANTHROPIC_API_KEY)")
        elif name == "openai":
            key = os.environ.get("OPENAI_API_KEY")
            if key:
                providers.append(
                    OpenAICompatibleProvider(
                        "openai",
                        settings.openai_model,
                        settings.openai_base_url,
                        key,
                        settings.llm_timeout_seconds,
                        settings.openai_reasoning_effort,
                    )
                )
            else:
                skipped.append("openai (no OPENAI_API_KEY)")
        elif name == "elastic":
            if settings.kibana_url:
                providers.append(ElasticAgentProvider(settings))
            else:
                skipped.append("elastic (no KUBECOMPASS_KIBANA_URL)")
        elif name == "ollama":
            # In auto mode only use Ollama if it is actually running.
            if auto and not _ollama_reachable(settings.ollama_base_url):
                skipped.append(f"ollama (not reachable at {settings.ollama_base_url})")
                continue
            providers.append(
                OpenAICompatibleProvider(
                    "ollama",
                    settings.ollama_model,
                    settings.ollama_base_url,
                    "ollama",
                    settings.ollama_timeout_seconds,
                    settings.ollama_reasoning_effort,
                )
            )
        else:
            skipped.append(f"{name} (unknown provider)")
    if skipped:
        log.info("LLM providers skipped: %s", ", ".join(skipped))
    if not providers:
        return NullLLMProvider("no LLM provider configured or reachable")
    log.info("LLM providers: %s", " → ".join(p.describe() for p in providers))
    provider: LLMProvider = providers[0] if len(providers) == 1 else ChainLLMProvider(providers)
    if settings.llm_daily_call_limit > 0:
        provider = BudgetedLLMProvider(provider, settings.llm_daily_call_limit)
    return provider
