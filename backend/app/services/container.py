"""Dependency wiring: one place that builds the service graph."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from elasticsearch import Elasticsearch

from app.agenda.service import AgendaService
from app.agenda.store import AttendeeStore
from app.agent.service import AgentService
from app.assistant.service import AssistantService
from app.config.settings import Settings, get_settings
from app.infrastructure.calibration import calibration_for
from app.infrastructure.elasticsearch import get_es
from app.infrastructure.embeddings import EmbeddingProvider, build_embedding_provider
from app.infrastructure.llm import LLMProvider, build_llm_provider
from app.knowledge_graph.service import GraphService
from app.knowledge_graph.store import ReadModelRegistry
from app.knowledge_graph.vocabulary import Vocabulary, get_vocabulary
from app.recommendation.scoring import load_ranking_config
from app.recommendation.service import RecommendationService
from app.search.service import SearchService


@dataclass
class Container:
    settings: Settings
    es: Elasticsearch
    embeddings: EmbeddingProvider
    llm: LLMProvider
    vocabulary: Vocabulary
    search: SearchService
    graph: GraphService
    read_models: ReadModelRegistry
    recommendations: RecommendationService
    attendees: AttendeeStore
    agenda: AgendaService
    assistant: AssistantService
    agent: AgentService


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    es = get_es()
    embeddings = build_embedding_provider(settings)
    llm = build_llm_provider(settings)
    vocab = get_vocabulary()
    search = SearchService(es, embeddings, settings)
    graph = GraphService()
    recs = RecommendationService(search, graph, embeddings, load_ranking_config(), vocab.low_signal)
    attendees = AttendeeStore(es)
    agenda = AgendaService(
        attendees, graph, vocab.low_signal, calibration_for(embeddings.model_name).alternative_min
    )
    assistant = AssistantService(search, graph, agenda, recs, llm, vocab)
    return Container(
        settings=settings,
        es=es,
        embeddings=embeddings,
        llm=llm,
        vocabulary=vocab,
        search=search,
        graph=graph,
        read_models=ReadModelRegistry(es),
        recommendations=recs,
        attendees=attendees,
        agenda=agenda,
        assistant=assistant,
        agent=AgentService(assistant),
    )


@lru_cache
def get_container() -> Container:
    return build_container()
