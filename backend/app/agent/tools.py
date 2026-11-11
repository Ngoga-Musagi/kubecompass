"""Typed agent tools over the existing services, with permission checks in the executor.

Every tool declares its input model, the permission it needs and whether it is *consequential*
(changes state the attendee owns). Consequential tools only run through `execute_confirmed`, which
the API calls after the attendee confirms a proposal; the planner can only propose them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.agenda.scheduling import Slot, conflicts_with
from app.agenda.service import AgendaError, AgendaService, AgendaView
from app.agenda.store import AttendeeState
from app.agent.permissions import AuditEntry, Permission
from app.config.conferences import ConferenceConfig
from app.knowledge_graph.service import GraphService
from app.knowledge_graph.store import ConferenceReadModel
from app.recommendation.service import Recommendation, RecommendationService
from app.schemas.api import SessionSummary, SpeakerBrief
from app.search.service import SearchService
from app.services.presenters import session_summary, speaker_brief


class ToolDenied(Exception):
    def __init__(self, tool: str, permission: Permission) -> None:
        super().__init__(f"{tool} needs the '{permission.value}' permission")
        self.tool = tool
        self.permission = permission


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ToolContext:
    rm: ConferenceReadModel
    conf: ConferenceConfig
    state: AttendeeState
    now: datetime
    search: SearchService
    graph: GraphService
    recommendations: RecommendationService
    agenda: AgendaService

    def summary(self, session_id: str) -> SessionSummary:
        return session_summary(self.rm.sessions[session_id], self.rm.speakers)

    def local_day(self, dt: datetime) -> date:
        return dt.astimezone(self.conf.tz).date()


# ---- inputs ------------------------------------------------------------------------------------
class NoInput(BaseModel):
    pass


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    day: date | None = None
    limit: int = Field(default=6, ge=1, le=20)


class SessionRef(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)


class FreeTimeInput(BaseModel):
    minutes: int = Field(default=60, ge=10, le=600)


class DayInput(BaseModel):
    day: date | None = None
    max_sessions: int = Field(default=6, ge=1, le=12)


# ---- outputs -----------------------------------------------------------------------------------
class SessionHit(BaseModel):
    session: SessionSummary
    reason: str | None = None
    in_agenda: bool = False
    fits_agenda: bool | None = None


class NextSession(BaseModel):
    session: SessionSummary | None
    starts_in_minutes: int | None = None
    happening_now: bool = False
    later_today: int = 0  # more saved sessions after this one, same day


class AgendaSuggestion(BaseModel):
    day: date | None
    picks: list[SessionHit]
    skipped_conflicts: int


class ActionResult(BaseModel):
    outcome: str  # done | already_done
    session: SessionSummary
    message: str


# ---- helpers -----------------------------------------------------------------------------------
def _saved(ctx: ToolContext) -> set[str]:
    return {i.session_id for i in ctx.state.agenda}


def _saved_slots(ctx: ToolContext) -> list[Slot]:
    return [
        s
        for s in (Slot.from_doc(ctx.rm.sessions[i]) for i in _saved(ctx) if i in ctx.rm.sessions)
        if s
    ]


def _hit(ctx: ToolContext, sid: str, reason: str | None = None) -> SessionHit:
    slot = Slot.from_doc(ctx.rm.sessions[sid])
    saved = sid in _saved(ctx)
    fits = None if saved or slot is None else not conflicts_with(slot, _saved_slots(ctx))
    return SessionHit(session=ctx.summary(sid), reason=reason, in_agenda=saved, fits_agenda=fits)


def _profile_recs(ctx: ToolContext) -> list[Recommendation]:
    # The profile is only used with the personalization permission, whichever tool asks.
    if ctx.state.profile is None or not ctx.state.agent.allows(Permission.PERSONALIZATION):
        return []
    rec = ctx.recommendations.recommend(ctx.rm, ctx.state.profile, agenda_ids=list(_saved(ctx)))
    return [*rec.must_attend, *rec.highly_relevant, *rec.explore]


# ---- tools -------------------------------------------------------------------------------------
def search_sessions(ctx: ToolContext, a: SearchInput) -> list[SessionHit]:
    res = ctx.search.search_sessions(ctx.rm.conference_id, a.query, mode="hybrid", size=a.limit * 3)
    out: list[SessionHit] = []
    for h in res.hits:
        sid = h.doc["id"]
        slot = Slot.from_doc(h.doc)
        if sid not in ctx.rm.sessions or (
            a.day and (not slot or ctx.local_day(slot.start) != a.day)
        ):
            continue
        out.append(_hit(ctx, sid))
        if len(out) >= a.limit:
            break
    return out


def search_speakers(ctx: ToolContext, a: SearchInput) -> list[SpeakerBrief]:
    hits = ctx.search.search_speakers(ctx.rm.conference_id, a.query, size=a.limit)
    return [speaker_brief(h.doc) for h in hits]


def get_session_details(ctx: ToolContext, a: SessionRef) -> SessionHit:
    if a.session_id not in ctx.rm.sessions:
        raise ToolError("unknown_session", "That session is not in this event's schedule.")
    return _hit(ctx, a.session_id)


def recommend_sessions(ctx: ToolContext, a: DayInput) -> list[SessionHit]:
    out = []
    for r in _profile_recs(ctx):
        slot = (
            Slot.from_doc(ctx.rm.sessions[r.session.id])
            if r.session.id in ctx.rm.sessions
            else None
        )
        if a.day and (not slot or ctx.local_day(slot.start) != a.day):
            continue
        out.append(_hit(ctx, r.session.id, r.explanation.summary))
        if len(out) >= a.max_sessions:
            break
    return out


def get_user_agenda(ctx: ToolContext, _: NoInput) -> AgendaView:
    return ctx.agenda.view(ctx.rm, ctx.conf, ctx.state)


def next_session(ctx: ToolContext, _: NoInput) -> NextSession:
    upcoming = sorted(
        (s for s in _saved_slots(ctx) if s.end > ctx.now), key=lambda s: (s.start, s.end)
    )
    if not upcoming:
        return NextSession(session=None)
    nxt = upcoming[0]
    same_day = [s for s in upcoming[1:] if ctx.local_day(s.start) == ctx.local_day(nxt.start)]
    return NextSession(
        session=ctx.summary(nxt.session_id),
        starts_in_minutes=max(0, int((nxt.start - ctx.now).total_seconds() // 60)),
        happening_now=nxt.start <= ctx.now < nxt.end,
        later_today=len(same_day),
    )


def sessions_in_free_time(ctx: ToolContext, a: FreeTimeInput) -> list[SessionHit]:
    """Sessions that start within the next 30 minutes and end inside the free window."""
    window_end = ctx.now + timedelta(minutes=a.minutes)
    soon = ctx.now + timedelta(minutes=30)
    saved_slots = _saved_slots(ctx)
    ranked = {r.session.id: (i, r.explanation.summary) for i, r in enumerate(_profile_recs(ctx))}
    cands: list[tuple[tuple[int, datetime], str, str | None]] = []
    for sid, doc in ctx.rm.sessions.items():
        slot = Slot.from_doc(doc)
        if not slot or not doc.get("is_content", True) or sid in _saved(ctx):
            continue
        if not (ctx.now - timedelta(minutes=5) <= slot.start <= soon and slot.end <= window_end):
            continue
        if conflicts_with(slot, saved_slots):
            continue
        rank, why = ranked.get(sid, (10_000, None))
        cands.append(((rank, slot.start), sid, why))
    cands.sort(key=lambda c: c[0])
    return [_hit(ctx, sid, why) for _, sid, why in cands[:6]]


def check_schedule_conflicts(ctx: ToolContext, _: NoInput) -> AgendaView:
    return ctx.agenda.view(ctx.rm, ctx.conf, ctx.state)


def suggest_agenda(ctx: ToolContext, a: DayInput) -> AgendaSuggestion:
    """Multi-step: personalized ranking → greedy conflict-free selection around saved sessions."""
    chosen = _saved_slots(ctx)
    picks: list[SessionHit] = []
    skipped = 0
    for r in _profile_recs(ctx):
        sid = r.session.id
        doc = ctx.rm.sessions.get(sid)
        slot = Slot.from_doc(doc) if doc else None
        if slot is None or sid in _saved(ctx) or slot.start < ctx.now:
            continue
        if a.day and ctx.local_day(slot.start) != a.day:
            continue
        if conflicts_with(slot, chosen):
            skipped += 1
            continue
        chosen.append(slot)
        picks.append(
            SessionHit(session=ctx.summary(sid), reason=r.explanation.summary, fits_agenda=True)
        )
        if len(picks) >= a.max_sessions:
            break
    picks.sort(key=lambda p: p.session.starts_at or datetime.max.replace(tzinfo=UTC))
    return AgendaSuggestion(day=a.day, picks=picks, skipped_conflicts=skipped)


def add_session_to_agenda(ctx: ToolContext, a: SessionRef) -> ActionResult:
    if a.session_id not in ctx.rm.sessions:
        raise ToolError("unknown_session", "That session is not in this event's schedule.")
    if a.session_id in _saved(ctx):  # idempotent: confirming twice is harmless
        return ActionResult(
            outcome="already_done",
            session=ctx.summary(a.session_id),
            message="Already in your agenda.",
        )
    try:
        ctx.state = ctx.agenda.add(ctx.rm, ctx.state, a.session_id)
    except AgendaError as exc:
        raise ToolError(exc.code, exc.message) from exc
    return ActionResult(
        outcome="done", session=ctx.summary(a.session_id), message="Added to your agenda."
    )


def remove_session_from_agenda(ctx: ToolContext, a: SessionRef) -> ActionResult:
    if a.session_id not in ctx.rm.sessions:
        raise ToolError("unknown_session", "That session is not in this event's schedule.")
    if a.session_id not in _saved(ctx):
        return ActionResult(
            outcome="already_done",
            session=ctx.summary(a.session_id),
            message="It wasn't in your agenda.",
        )
    ctx.state = ctx.agenda.remove(ctx.state, a.session_id)
    return ActionResult(
        outcome="done", session=ctx.summary(a.session_id), message="Removed from your agenda."
    )


# ---- registry ----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    permission: Permission
    input_model: type[BaseModel]
    fn: Callable[[ToolContext, Any], Any]
    consequential: bool = False


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "search_sessions",
            "Hybrid search over this event's sessions",
            Permission.READ,
            SearchInput,
            search_sessions,
        ),
        Tool(
            "search_speakers",
            "Search this event's speakers",
            Permission.READ,
            SearchInput,
            search_speakers,
        ),
        Tool(
            "get_session_details",
            "One session with agenda fit",
            Permission.READ,
            SessionRef,
            get_session_details,
        ),
        Tool(
            "recommend_sessions",
            "Personalized, explained recommendations",
            Permission.PERSONALIZATION,
            DayInput,
            recommend_sessions,
        ),
        Tool(
            "sessions_in_free_time",
            "Sessions starting soon that fit a free window",
            Permission.READ,
            FreeTimeInput,
            sessions_in_free_time,
        ),
        Tool(
            "get_user_agenda",
            "The attendee's agenda with conflicts and gaps",
            Permission.AGENDA,
            NoInput,
            get_user_agenda,
        ),
        Tool(
            "next_session",
            "Next saved session and where it is",
            Permission.AGENDA,
            NoInput,
            next_session,
        ),
        Tool(
            "check_schedule_conflicts",
            "Overlaps in the attendee's agenda",
            Permission.AGENDA,
            NoInput,
            check_schedule_conflicts,
        ),
        Tool(
            "suggest_agenda",
            "Build a conflict-free agenda from recommendations",
            Permission.PERSONALIZATION,
            DayInput,
            suggest_agenda,
        ),
        Tool(
            "add_session_to_agenda",
            "Save a session to the agenda",
            Permission.AGENDA,
            SessionRef,
            add_session_to_agenda,
            consequential=True,
        ),
        Tool(
            "remove_session_from_agenda",
            "Remove a session from the agenda",
            Permission.AGENDA,
            SessionRef,
            remove_session_from_agenda,
            consequential=True,
        ),
    ]
}


def _check(ctx: ToolContext, tool: Tool) -> None:
    if not ctx.state.agent.allows(tool.permission):
        raise ToolDenied(tool.name, tool.permission)


def run_tool(ctx: ToolContext, name: str, args: dict[str, Any] | None = None) -> Any:
    """Run a read-style tool for the planner. Consequential tools cannot run this way."""
    tool = TOOLS[name]
    if tool.consequential:
        raise ToolError("needs_confirmation", f"{name} must be confirmed by the attendee")
    _check(ctx, tool)
    return tool.fn(ctx, tool.input_model.model_validate(args or {}))


def execute_confirmed(ctx: ToolContext, name: str, args: dict[str, Any]) -> ActionResult:
    """Run a consequential tool after the attendee confirmed it; audited, idempotent."""
    tool = TOOLS.get(name)
    if tool is None or not tool.consequential:
        raise ToolError("unknown_action", "That action is not available.")
    _check(ctx, tool)
    parsed = tool.input_model.model_validate(args)
    try:
        result: ActionResult = tool.fn(ctx, parsed)
    except ToolError as exc:
        ctx.state.agent.record(
            AuditEntry(
                at=datetime.now(UTC),
                tool=name,
                args=parsed.model_dump(),
                outcome="failed",
                detail=exc.code,
            )
        )
        raise
    ctx.state.agent.record(
        AuditEntry(
            at=datetime.now(UTC), tool=name, args=parsed.model_dump(), outcome=result.outcome
        )
    )
    return result
