"""Conference assistant: retrieval-augmented answers grounded in indexed conference data.

It reuses the same search, graph and agenda services as the rest of the product.
With an LLM it writes a concise answer citing [S#]/[P#] records; without one it
returns a transparent retrieval-only answer. It never answers from model memory.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agenda.service import AgendaService
from app.agenda.store import AttendeeState
from app.config.conferences import ConferenceConfig
from app.infrastructure.calibration import calibration_for
from app.infrastructure.llm import LLMProvider, LLMText, LLMUnavailableError
from app.knowledge_graph.extractor import match_text
from app.knowledge_graph.service import GraphService
from app.knowledge_graph.store import ConferenceReadModel
from app.knowledge_graph.vocabulary import Vocabulary
from app.recommendation.service import RecommendationService
from app.schemas.api import SessionSummary, SpeakerBrief
from app.search.service import SearchService
from app.services.presenters import session_summary, speaker_brief

log = logging.getLogger(__name__)

Intent = Literal["sessions", "speakers", "agenda_gaps", "related", "explain"]
_SPEAKER_Q = re.compile(r"\b(who('s| is)?|speakers?|presenters?|people|experts?)\b", re.I)
_AGENDA_Q = re.compile(
    r"\b(my agenda|my schedule|am i missing|what am i missing|should i add|"
    r"gaps? in my)\b",
    re.I,
)
_RELATED_Q = re.compile(r"\b(related to this|similar to this|this session|this talk)\b", re.I)
_EXPLAIN_Q = re.compile(r"^\s*(what is|what are|explain|define|tell me about)\b", re.I)
_CITE = re.compile(r"\[(S|P)(\d+)\]")
# Question scaffolding that should not be sent to search ("who is speaking about X" -> "X").
_SCAFFOLD = re.compile(
    r"^\s*(please\s+)?(can you\s+)?(tell me\s+)?(which|what|who|are there|is there|any|show me|"
    r"find|list|give me)?\s*(sessions?|talks?|speakers?|people|presenters?|ones)?\s*"
    r"(is|are|'s)?\s*(speaking|talking|presenting|working|discuss(es|ing)?|cover(s|ing)?|"
    r"about|on|regarding|related to|that)?\s*(about|on|with|regarding)?\s*",
    re.I,
)
# Coverage threshold: per embedding model, see deployment/configuration/embedding-calibration.yaml


def topic_query(message: str) -> str:
    stripped = _SCAFFOLD.sub("", message).strip(" ?.!")
    return stripped if len(stripped) >= 3 else message.strip(" ?.!")


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)
    context_session_id: str | None = None


class Citation(BaseModel):
    ref: str  # S1 / P1
    kind: Literal["session", "speaker"]
    id: str
    title: str


class ConceptLink(BaseModel):
    id: str
    name: str
    type: str
    relation: str
    origin: str  # explicit / extracted / curated / inferred
    evidence: str | None = None


class ChatResponse(BaseModel):
    answer: str
    mode: Literal["llm", "retrieval_only", "no_results"]
    intent: Intent
    sessions: list[SessionSummary]
    speakers: list[SpeakerBrief]
    citations: list[Citation]
    concepts: list[ConceptLink]
    notice: str | None = None
    generated_by: str | None = None  # "provider:model" when mode == "llm"


SYSTEM_PROMPT = """You are the KubeCompass conference assistant for {conference}.
Answer ONLY from the conference records provided in the user message. Records are labelled
[S1], [S2]... for sessions and [P1], [P2]... for speakers.

Rules:
- Cite every claim about a session or speaker with its label, e.g. "...GPU sharing [S2]".
- Never invent sessions, speakers, times, rooms, companies or expertise. If the records do not
  answer the question, say so plainly and suggest a better search.
- Relationships marked "inferred" or "extracted" are connections the application derived; describe
  them as likely connections, not confirmed facts. Information marked "explicit" comes from the
  official schedule.
- You may briefly explain a general technical concept to give context, but keep it clearly
  separate from statements about the conference and do not attribute it to any speaker.
- Be concise: at most about 180 words, using short paragraphs or a short bulleted list.
- Times are local conference time ({timezone})."""


def classify(message: str, has_context: bool) -> Intent:
    if _AGENDA_Q.search(message):
        return "agenda_gaps"
    if has_context and _RELATED_Q.search(message):
        return "related"
    if _SPEAKER_Q.search(message):
        return "speakers"
    if _EXPLAIN_Q.search(message):
        return "explain"
    return "sessions"


def _session_record(i: int, doc: dict[str, Any]) -> str:
    t = doc.get("time") or {}
    ents = "; ".join(f"{e['name']} ({e['origin']})" for e in doc.get("entities", [])[:8])
    return (
        f"[S{i}] {doc['title']}\n  when: {t.get('starts_at_local', 'unscheduled')} | room: "
        f"{(doc.get('room') or {}).get('name', 'n/a')} | track: {doc.get('track')} | format: "
        f"{doc.get('format')} | level: {doc.get('audience_level') or 'n/a'}\n"
        f"  speakers: {', '.join(doc.get('speaker_names', [])) or 'none listed'}\n"
        f"  linked concepts: {ents or 'none'}\n"
        f"  abstract (explicit): {(doc.get('description') or 'no abstract')[:900]}"
    )


def _speaker_record(i: int, doc: dict[str, Any], titles: list[str]) -> str:
    exp = "; ".join(f"{e['name']} ({e['origin']})" for e in doc.get("entities", [])[:6])
    return (
        f"[P{i}] {doc['full_name']} | {doc.get('job_title') or ''} {doc.get('company') or ''}\n"
        f"  sessions (explicit): {'; '.join(titles) or 'none'}\n"
        f"  bio mentions (extracted): {exp or 'none'}\n"
        f"  bio (explicit): {(doc.get('bio') or 'no bio')[:500]}"
    )


class AssistantService:
    def __init__(
        self,
        search: SearchService,
        graph: GraphService,
        agenda: AgendaService,
        recommendations: RecommendationService,
        llm: LLMProvider,
        vocab: Vocabulary,
    ) -> None:
        self.search = search
        self.graph = graph
        self.agenda = agenda
        self.recs = recommendations
        self.llm = llm
        self.vocab = vocab

    def _concepts(self, rm: ConferenceReadModel, message: str) -> list[ConceptLink]:
        out: list[ConceptLink] = []
        for m in match_text(self.vocab, message, None):
            key = m.entry.key
            if key not in rm.entities:
                continue
            if any(c.id == key for c in out):
                continue
            out.append(
                ConceptLink(
                    id=key,
                    name=m.entry.name,
                    type=m.entry.type.value,
                    relation="mentioned",
                    origin="explicit",
                )
            )
            for other, data in rm.graph.neighbors(key):
                if (
                    data["type"] in ("PART_OF", "RELATED_TO")
                    and other in rm.entities
                    and len(out) < 12
                    and all(c.id != other for c in out)
                ):
                    out.append(
                        ConceptLink(
                            id=other,
                            name=rm.entities[other]["name"],
                            type=rm.entities[other]["type"],
                            relation=f"{data['type']} {m.entry.name}",
                            origin=data["origin"],
                            evidence=data.get("evidence"),
                        )
                    )
        return out

    def chat(
        self,
        rm: ConferenceReadModel,
        conf: ConferenceConfig,
        req: ChatRequest,
        state: AttendeeState | None,
    ) -> ChatResponse:
        intent = classify(req.message, bool(req.context_session_id))
        sessions: list[dict[str, Any]] = []
        speakers: list[dict[str, Any]] = []
        notice: str | None = None
        covered = False

        if intent == "agenda_gaps":
            if state is None or state.profile is None:
                notice = (
                    "Set your interest profile on the Discover page so I can compare it "
                    "with your agenda."
                )
            else:
                rec = self.recs.recommend(
                    rm, state.profile, agenda_ids=[i.session_id for i in state.agenda]
                )
                top = [
                    r.session.id
                    for r in [*rec.must_attend, *rec.highly_relevant]
                    if not r.agenda.in_agenda
                ]
                fits = self.agenda.free_fits(rm, state, top)
                sessions = [rm.sessions[s] for s in (fits or top)[:6]]
                covered = bool(sessions)
                notice = (
                    "Recommended sessions you have not saved that fit your current agenda."
                    if fits
                    else "These relevant sessions overlap with your agenda."
                )
        elif intent == "related" and req.context_session_id in rm.sessions:
            rel = self.graph.related_sessions(rm, req.context_session_id, limit=6)
            sessions = [rm.sessions[r.session.id] for r in rel]
            covered = bool(sessions)
        else:
            query = topic_query(req.message)
            result = self.search.search_sessions(rm.conference_id, query, mode="hybrid", size=8)
            sims = [h.vector_similarity for h in result.hits if h.vector_similarity is not None]
            if sims:
                covered = (
                    max(sims) >= calibration_for(self.search.embeddings.model_name).coverage_min
                )
            else:  # embeddings unavailable: fall back to "some lexical match exists"
                covered = any(h.bm25_rank is not None for h in result.hits)
            sessions = [h.doc for h in result.hits[:6]] if covered else []
            if intent == "speakers" and covered:
                hits = self.search.search_speakers(rm.conference_id, query, size=6)
                speakers = [h.doc for h in hits]

        concepts = self._concepts(rm, req.message)
        session_out = [session_summary(d, rm.speakers) for d in sessions]
        speaker_out = [speaker_brief(d) for d in speakers]
        citations = [
            Citation(ref=f"S{i}", kind="session", id=d["id"], title=d["title"])
            for i, d in enumerate(sessions, 1)
        ]
        citations += [
            Citation(ref=f"P{i}", kind="speaker", id=d["id"], title=d["full_name"])
            for i, d in enumerate(speakers, 1)
        ]

        if not covered:
            return ChatResponse(
                answer=(
                    notice
                    or "I couldn't find sessions or speakers in the indexed "
                    f"{conf.short_name} data that match that question. Try different "
                    "wording, or browse related topics below."
                ),
                mode="no_results",
                intent=intent,
                sessions=[],
                speakers=[],
                citations=[],
                concepts=concepts,
                notice=notice,
            )

        if self.llm.available:
            try:
                generated = self._generate(rm, conf, req, sessions, speakers, notice)
                answer = generated.text
                valid = {c.ref for c in citations}
                used = {f"{k}{n}" for k, n in _CITE.findall(answer)} & valid
                if not used:
                    # Grounding guard: an answer that cites none of the provided records is
                    # not shown (small local models occasionally answer from memory).
                    raise LLMUnavailableError(f"{generated.served_by} answer cited no records")
                answer = _CITE.sub(
                    lambda m: m.group(0) if f"{m.group(1)}{m.group(2)}" in valid else "", answer
                )
                return ChatResponse(
                    answer=answer,
                    mode="llm",
                    generated_by=generated.served_by,
                    intent=intent,
                    sessions=session_out,
                    speakers=speaker_out,
                    citations=[c for c in citations if c.ref in used],
                    concepts=concepts,
                    notice=notice,
                )
            except LLMUnavailableError as exc:
                log.info("Assistant LLM unavailable: %s", exc)
                notice = (
                    notice + " " if notice else ""
                ) + "AI summary unavailable; showing matching records."
        return ChatResponse(
            answer=_extractive_answer(req.message, intent, sessions, speakers, notice),
            mode="retrieval_only",
            intent=intent,
            sessions=session_out,
            speakers=speaker_out,
            citations=citations,
            concepts=concepts,
            notice=notice,
        )

    def _generate(
        self,
        rm: ConferenceReadModel,
        conf: ConferenceConfig,
        req: ChatRequest,
        sessions: list[dict[str, Any]],
        speakers: list[dict[str, Any]],
        notice: str | None,
    ) -> LLMText:
        records = [_session_record(i, d) for i, d in enumerate(sessions, 1)]
        for i, d in enumerate(speakers, 1):
            titles = [rm.sessions[s]["title"] for s in d.get("session_ids", []) if s in rm.sessions]
            records.append(_speaker_record(i, d, titles))
        history = "\n".join(f"{t.role}: {t.content[:600]}" for t in req.history[-4:])
        user = (
            (f"Earlier conversation:\n{history}\n\n" if history else "")
            + (f"Context: {notice}\n\n" if notice else "")
            + "Conference records:\n"
            + "\n\n".join(records)
            + f"\n\nQuestion: {req.message}"
        )
        system = SYSTEM_PROMPT.format(conference=conf.name, timezone=conf.timezone)
        return self.llm.complete(system, user, max_tokens=1200)


def _extractive_answer(
    message: str,
    intent: Intent,
    sessions: list[dict[str, Any]],
    speakers: list[dict[str, Any]],
    notice: str | None,
) -> str:
    """Without an LLM: a one-line, factual lead; the cited records are rendered as cards."""
    parts: list[str] = []
    if notice:
        parts.append(notice)
    if speakers:
        refs = " ".join(f"[P{i}]" for i in range(1, len(speakers) + 1))
        parts.append(f"{len(speakers)} speakers in the conference data match “{message}” {refs}.")
    if sessions:
        refs = " ".join(f"[S{i}]" for i in range(1, len(sessions) + 1))
        what = "related sessions" if speakers else "sessions from the official schedule"
        parts.append(f"{len(sessions)} {what} match {refs}.")
    return " ".join(parts)
