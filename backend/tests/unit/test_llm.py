"""LLM provider chain, provider selection and the LLM/rules profile merge (no network)."""

from __future__ import annotations

import pytest

from app.config.settings import get_settings
from app.infrastructure import llm as llm_mod
from app.infrastructure.llm import (
    ChainLLMProvider,
    LLMText,
    LLMUnavailableError,
    NullLLMProvider,
    build_llm_provider,
)
from app.recommendation.profile import LLMIntentParser, RuleBasedIntentParser


class Fake:
    def __init__(self, name: str, fail: LLMUnavailableError | None = None, structured=None):
        self.name = name
        self.fail = fail
        self.calls = 0
        self._structured = structured

    available = True

    def describe(self) -> str:
        return f"{self.name}:m"

    def complete(self, system, user, *, max_tokens=2048):
        self.calls += 1
        if self.fail:
            raise self.fail
        return LLMText("ok [S1]", self.describe())

    def structured(self, system, user, schema):
        self.calls += 1
        if self.fail:
            raise self.fail
        return schema.model_validate(self._structured)


def test_chain_falls_through_and_pauses_permanently_failing_provider():
    broke = Fake("anthropic", LLMUnavailableError("no credits", permanent=True))
    local = Fake("ollama")
    chain = ChainLLMProvider([broke, local])
    assert chain.complete("s", "u").served_by == "ollama:m"
    assert chain.complete("s", "u").served_by == "ollama:m"
    assert broke.calls == 1  # paused after the first permanent failure
    assert "paused" in chain.describe()


def test_chain_raises_when_every_provider_fails():
    chain = ChainLLMProvider(
        [Fake("a", LLMUnavailableError("x")), Fake("b", LLMUnavailableError("y"))]
    )
    with pytest.raises(LLMUnavailableError, match="x; y"):
        chain.complete("s", "u")


def test_build_selects_providers_from_config(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_PROFILE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # Independent of the developer's .env (which may configure Kibana / other providers).
    s = get_settings().model_copy(update={"kibana_url": None})
    assert isinstance(
        build_llm_provider(s.model_copy(update={"llm_provider": "none"})), NullLLMProvider
    )
    p = build_llm_provider(s.model_copy(update={"llm_provider": "openai"}))
    assert p.describe() == f"openai:{s.openai_model}"
    # auto: anthropic skipped (no key); ollama only if reachable
    monkeypatch.setattr(llm_mod, "_ollama_reachable", lambda url: True)
    chain = build_llm_provider(s.model_copy(update={"llm_provider": "auto"}))
    assert chain.describe() == f"openai:{s.openai_model} → ollama:{s.ollama_model}"
    monkeypatch.setattr(llm_mod, "_ollama_reachable", lambda url: False)
    single = build_llm_provider(s.model_copy(update={"llm_provider": "auto"}))
    assert single.describe().startswith("openai:")


def test_llm_profile_merge_keeps_text_grounded_constraints(vocabulary):
    available = set(vocabulary.entries)
    rules = RuleBasedIntentParser(vocabulary, available)
    catalog = {e.name: e.key for e in vocabulary.entries.values()}
    # A small model over-generalizes the exclusion and misses one interest and the level.
    fake = Fake(
        "ollama",
        structured={
            "primary_interests": ["GPU Scheduling & Sharing", "Not A Real Topic"],
            "secondary_interests": ["AI Infrastructure"],
            "learning_goals": ["Schedule GPUs well"],
            "preferred_formats": ["talk"],
            "experience_level": "intermediate",
            "excluded_topics": ["Security", "Policy as Code", "Supply Chain Security"],
        },
    )
    p = LLMIntentParser(fake, rules, catalog).parse(
        "I want GPU scheduling and autoscaling. Not interested in security. Advanced demos please."
    )
    labels = [i.label for i in p.primary_interests]
    assert labels[0] == "GPU Scheduling & Sharing"
    assert "Autoscaling" in labels  # rule finding kept
    assert "Not A Real Topic" not in labels  # ungrounded LLM output dropped
    assert [e.label for e in p.excluded_topics] == ["Security"]  # rules win
    assert p.experience_level == "advanced" and p.preferred_formats == ["demo"]
    assert p.learning_goals == ["Schedule GPUs well"] and p.parser == "llm"


def test_llm_parser_falls_back_to_rules(vocabulary):
    rules = RuleBasedIntentParser(vocabulary, set(vocabulary.entries))
    broken = Fake("ollama", LLMUnavailableError("offline"))
    p = LLMIntentParser(broken, rules, {}).parse("I want to learn about eBPF.")
    assert p.parser == "rules" and [i.label for i in p.primary_interests] == ["eBPF"]


def test_daily_budget_falls_back_after_limit():
    from app.infrastructure.llm import BudgetedLLMProvider

    inner = Fake("openai")
    p = BudgetedLLMProvider(inner, daily_limit=2)
    p.complete("s", "u")
    p.complete("s", "u")
    with pytest.raises(LLMUnavailableError, match="budget"):
        p.complete("s", "u")
    assert inner.calls == 2 and "2/2" in p.describe()
