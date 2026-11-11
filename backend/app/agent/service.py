"""The attendee's event agent: plan → permission-checked tools → structured, speakable reply.

Routing is deterministic for time-aware and agenda tasks (fast, testable, works without an LLM);
open questions go to the grounded RAG assistant. The LLM never chooses or executes tools, so text
inside session abstracts cannot trigger actions. Consequential tools are only *proposed* here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agenda.service import AgendaView
from app.agent.permissions import Permission
from app.agent.tools import (
    TOOLS,
    AgendaSuggestion,
    NextSession,
    SessionHit,
    ToolContext,
    ToolDenied,
    run_tool,
)
from app.assistant.service import AssistantService, ChatRequest, ChatTurn, Citation, topic_query
from app.schemas.api import SessionSummary, SpeakerBrief

AgentIntent = Literal[
    "next_session",
    "free_time",
    "happening_now",
    "build_agenda",
    "show_agenda",
    "conflicts",
    "add",
    "remove",
    "recommend",
    "calendar_sync",
    "ask",
]

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_RULES: list[tuple[AgentIntent, re.Pattern[str]]] = [
    (
        "calendar_sync",
        re.compile(
            r"\b(sync|synchroni[sz]e)\b|\bgoogle calendar\b|\b(to|in|into) my calendar\b", re.I
        ),
    ),
    (
        "conflicts",
        re.compile(r"\b(conflicts?|overlap(s|ping)?|clash(es)?|double[- ]booked)\b", re.I),
    ),
    (
        "next_session",
        re.compile(
            r"\b(next session|my next|attend next|go next|where (do|should) i (go|be)|"
            r"what('s| is) next( for me)?|where is my)\b",
            re.I,
        ),
    ),
    (
        "free_time",
        re.compile(
            r"\b(\d+|an?|half an?)\s*(min(ute)?s?|hours?|hrs?)\b.*\b(free|spare|gap|break|kill)\b|"
            r"\b(free|spare)\b.*\b(\d+|an?|half an?)\s*(min(ute)?s?|hours?)\b|\bfree (time|slot)\b",
            re.I,
        ),
    ),
    (
        "happening_now",
        re.compile(
            r"\b(happening|going on|on) (right )?now\b|\bright now\b|\bnext room\b|"
            r"\bstarting soon\b",
            re.I,
        ),
    ),
    (
        "build_agenda",
        re.compile(
            r"\b(build|plan|create|make|optimi[sz]e|fill|organi[sz]e|suggest)\b.{0,20}"
            r"\b(agenda|schedule|day|itinerary)\b",
            re.I,
        ),
    ),
    ("remove", re.compile(r"^\s*(please\s+)?(remove|drop|delete|unsave|take)\b", re.I)),
    ("add", re.compile(r"^\s*(please\s+)?(add|save|bookmark|put)\b", re.I)),
    (
        "show_agenda",
        re.compile(r"\b(my agenda|my schedule|what('s| is) on my|saved sessions)\b", re.I),
    ),
    (
        "recommend",
        re.compile(
            r"\b(recommend|suggest|what should i (attend|see|watch)|best sessions|for me)\b", re.I
        ),
    ),
]
_DURATION = re.compile(
    r"(\d+)\s*(min|minute|minutes|hour|hours|hr|hrs)\b|(half an hour)|(an hour)", re.I
)
_ADD_SCAFFOLD = re.compile(
    r"^\s*(please\s+)?(add|save|bookmark|put|remove|drop|delete|unsave|take)\s+(the\s+)?"
    r"(session|talk)?\s*(about|on|called|named)?\s*|\s*(to|from|in|on|off)\s+(my\s+)?"
    r"(agenda|schedule|calendar)\s*\.?$",
    re.I,
)


class ProposedAction(BaseModel):
    tool: str
    args: dict[str, str]
    label: str
    description: str


class Card(BaseModel):
    type: Literal["session", "speaker", "conflict", "agenda_summary", "action", "notice"]
    title: str | None = None
    detail: str | None = None
    badge: str | None = None
    session: SessionSummary | None = None
    speaker: SpeakerBrief | None = None
    action: ProposedAction | None = None
    in_agenda: bool = False
    fits_agenda: bool | None = None


class ToolTrace(BaseModel):
    tool: str
    status: Literal["ok", "denied", "error"]
    detail: str | None = None


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)
    context_session_id: str | None = None
    now: datetime | None = Field(
        default=None, description="Override the current time (demo/testing)"
    )


class AgentReply(BaseModel):
    reply: str  # short, plain text; safe to speak aloud
    intent: AgentIntent
    cards: list[Card] = Field(default_factory=list)
    trace: list[ToolTrace] = Field(default_factory=list)
    needs_permission: Permission | None = None
    mode: Literal["agent", "llm", "retrieval_only", "no_results"] = "agent"
    citations: list[Citation] = Field(default_factory=list)  # [S#]/[P#] in `reply`
    generated_by: str | None = None


def classify(message: str) -> AgentIntent:
    for intent, rx in _RULES:
        if rx.search(message):
            return intent
    return "ask"


def parse_minutes(message: str, default: int = 60) -> int:
    m = _DURATION.search(message)
    if not m:
        return default
    if m.group(3):
        return 30
    if m.group(4):
        return 60
    n = int(m.group(1))
    return n * 60 if m.group(2).lower().startswith(("h",)) else n


def parse_day(message: str, now: datetime, days: list[date]) -> date | None:
    text = message.lower()
    today = now.date()
    if "today" in text:
        return today
    if "tomorrow" in text:
        return today + timedelta(days=1)
    for d in days:
        month_day = (f"{d:%b} {d.day}".lower(), f"{d:%B} {d.day}".lower())
        if re.search(rf"\b{_DAYS[d.weekday()]}\b", text) or any(m in text for m in month_day):
            return d
    return None


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _when(s: SessionSummary) -> str:
    """'Thursday at 1:50 PM' in the event's local time (starts_at carries the event offset)."""
    if s.starts_at is None:
        return "time not published"
    t = s.starts_at
    return f"{t:%A} at {t.strftime('%I:%M %p').lstrip('0')}"


def _where(s: SessionSummary) -> str:
    """'Salt Lake Ballroom DE, Hyatt Regency' from 'Hyatt Regency | Level 2 | Salt Lake …'."""
    if not s.room:
        return s.venue or "a room not published yet"
    name = s.room.split("|")[-1].strip()
    venue = s.venue or s.room.split("|")[0].strip()
    return f"{name}, {venue}" if venue and venue.lower() not in name.lower() else name


def _session_card(hit: SessionHit, badge: str | None = None) -> Card:
    return Card(
        type="session",
        session=hit.session,
        detail=hit.reason,
        badge=badge,
        in_agenda=hit.in_agenda,
        fits_agenda=hit.fits_agenda,
    )


def _add_action(s: SessionSummary) -> ProposedAction:
    return ProposedAction(
        tool="add_session_to_agenda",
        args={"session_id": s.id},
        label="Add to agenda",
        description=f"Add “{s.title}” to your agenda",
    )


Call = Callable[..., Any]


def _offer(cards: list[Card]) -> list[Card]:
    """Attach an add-to-agenda proposal to session cards not yet saved."""
    for c in cards:
        if c.session and not c.in_agenda:
            c.action = _add_action(c.session)
    return cards


class AgentService:
    def __init__(self, assistant: AssistantService) -> None:
        self.assistant = assistant

    def handle(self, ctx: ToolContext, req: AgentChatRequest) -> AgentReply:
        intent = classify(req.message)
        trace: list[ToolTrace] = []

        def call(name: str, args: dict[str, Any] | None = None) -> Any:
            try:
                out = run_tool(ctx, name, args)
            except ToolDenied:
                perm = TOOLS[name].permission.value
                trace.append(ToolTrace(tool=name, status="denied", detail=perm))
                raise
            trace.append(ToolTrace(tool=name, status="ok"))
            return out

        handler = getattr(self, f"_{intent}")
        try:
            reply: AgentReply = handler(ctx, req, call)
        except ToolDenied as exc:
            reply = AgentReply(
                reply=_DENIED[exc.permission],
                intent=intent,
                needs_permission=exc.permission,
                cards=[
                    Card(type="notice", title="Permission needed", detail=_DENIED[exc.permission])
                ],
            )
        reply.intent = intent
        reply.trace = trace + reply.trace
        return reply

    @staticmethod
    def _day(ctx: ToolContext, req: AgentChatRequest) -> date | None:
        days = sorted(
            {
                ctx.local_day(datetime.fromisoformat(d["time"]["starts_at"]))
                for d in ctx.rm.sessions.values()
                if d.get("time")
            }
        )
        return parse_day(req.message, ctx.now.astimezone(ctx.conf.tz), days)

    # ---- intents -------------------------------------------------------------------------------
    def _next_session(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        nxt: NextSession = call("next_session")
        if nxt.session is None:
            soon: list[SessionHit] = call("sessions_in_free_time", {"minutes": 90})
            cards = _offer([_session_card(h, "Starting soon") for h in soon[:3]])
            more = (
                f"{_n(len(cards), 'session')} start soon that you could join."
                if cards
                else "Nothing else starts in the next half hour."
            )
            return AgentReply(
                intent="next_session",
                cards=cards,
                reply=f"You have no upcoming sessions saved. {more}",
            )
        s = nxt.session
        if nxt.happening_now:
            when = "happening now"
        elif (nxt.starts_in_minutes or 0) < 180:
            when = f"starting in {nxt.starts_in_minutes} minutes"
        else:
            when = f"starting {_when(s)}"
        text = f"Your next session is “{s.title}”, {when}, in {_where(s)}."
        if nxt.later_today:
            text += f" You have {nxt.later_today} more later that day."
        card = Card(type="session", session=s, badge="Next", in_agenda=True)
        return AgentReply(intent="next_session", reply=text, cards=[card])

    def _free_time(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        return self._soon(call, parse_minutes(req.message), "free_time")

    def _happening_now(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        return self._soon(call, 90, "happening_now")

    def _soon(self, call: Call, minutes: int, intent: AgentIntent) -> AgentReply:
        hits: list[SessionHit] = call("sessions_in_free_time", {"minutes": minutes})
        if not hits:
            return AgentReply(
                intent=intent,
                reply=f"Nothing starts in the next half hour that fits {minutes} free minutes. "
                "It's a good moment for the hallway track.",
            )
        first = hits[0].session
        return AgentReply(
            intent=intent,
            cards=_offer([_session_card(h, "Starting soon") for h in hits]),
            reply=f"{_n(len(hits), 'session')} fit. The best match is “{first.title}”, "
            f"{_when(first)}, in {_where(first)}.",
        )

    def _build_agenda(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        day = self._day(ctx, req)
        sug: AgendaSuggestion = call("suggest_agenda", {"day": day.isoformat() if day else None})
        if ctx.state.profile is None:
            return AgentReply(
                intent="build_agenda",
                reply="Tell me what you want to learn first, then I can build your agenda.",
            )
        on_day = f" on {day:%A}" if day else ""
        if not sug.picks:
            return AgentReply(
                intent="build_agenda",
                reply=f"I couldn't find more relevant sessions that fit your agenda{on_day}.",
            )
        skipped = (
            f" I left out {_n(sug.skipped_conflicts, 'relevant session')} that would conflict."
            if sug.skipped_conflicts
            else ""
        )
        return AgentReply(
            intent="build_agenda",
            cards=_offer([_session_card(p) for p in sug.picks]),
            reply=f"Here's a conflict-free plan with {_n(len(sug.picks), 'session')}{on_day}. "
            f"Confirm the ones you want to save.{skipped}",
        )

    def _show_agenda(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        view: AgendaView = call("get_user_agenda")
        upcoming = [
            e
            for d in view.days
            for e in d.entries
            if e.session.ends_at is None or e.session.ends_at > ctx.now
        ][:6]
        cards = _conflict_cards(view) + [
            Card(
                type="session",
                session=e.session,
                in_agenda=True,
                badge="Conflict" if e.conflicts_with else None,
            )
            for e in upcoming
        ]
        status = (
            f" and {_n(len(view.conflicts), 'conflict')} to resolve."
            if view.conflicts
            else " with no conflicts."
        )
        return AgentReply(
            intent="show_agenda",
            reply=f"You have {_n(view.total, 'session')} saved{status}",
            cards=cards,
        )

    def _conflicts(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        view: AgendaView = call("check_schedule_conflicts")
        text = (
            f"You have {_n(len(view.conflicts), 'conflict')}. Open My Agenda to pick alternatives."
            if view.conflicts
            else "No conflicts. Your agenda fits together."
        )
        return AgentReply(intent="conflicts", reply=text, cards=_conflict_cards(view))

    def _add(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        return self._change(ctx, req, call, adding=True)

    def _remove(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        return self._change(ctx, req, call, adding=False)

    def _change(
        self, ctx: ToolContext, req: AgentChatRequest, call: Call, *, adding: bool
    ) -> AgentReply:
        intent: AgentIntent = "add" if adding else "remove"
        if not ctx.state.agent.allows(Permission.AGENDA):
            raise ToolDenied("add_session_to_agenda", Permission.AGENDA)
        target = self._target(ctx, req, call)
        if target is None:
            return AgentReply(
                intent=intent,
                reply="Which session do you mean? Say its title, or open the session and ask.",
            )
        s = target.session
        if adding and target.in_agenda:
            reply = f"“{s.title}” is already in your agenda."
            return AgentReply(intent=intent, reply=reply, cards=[_session_card(target)])
        if not adding and not target.in_agenda:
            reply = f"“{s.title}” isn't in your agenda."
            return AgentReply(intent=intent, reply=reply, cards=[_session_card(target)])
        if adding:
            action = _add_action(s)
            text = f"Add “{s.title}” ({_when(s)}, {_where(s)}) to your agenda?"
            if target.fits_agenda is False:
                text += " It overlaps with a session you saved."
        else:
            action = ProposedAction(
                tool="remove_session_from_agenda",
                args={"session_id": s.id},
                label="Remove",
                description=f"Remove “{s.title}” from your agenda",
            )
            text = f"Remove “{s.title}” from your agenda?"
        card = Card(
            type="action",
            title="Please confirm",
            session=s,
            action=action,
            in_agenda=target.in_agenda,
            fits_agenda=target.fits_agenda,
        )
        return AgentReply(intent=intent, reply=text, cards=[card])

    def _calendar_sync(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        cal = ctx.calendar
        if cal is None or not cal.configured:
            return AgentReply(
                intent="calendar_sync",
                reply="Google Calendar isn't set up on this server yet. "
                "You can download your agenda as a calendar file from My Agenda instead.",
            )
        if not ctx.state.agent.allows(Permission.INTEGRATIONS) or not cal.connected(
            ctx.state.guest_id
        ):
            raise ToolDenied("sync_agenda_to_calendar", Permission.INTEGRATIONS)
        if not ctx.state.agent.allows(Permission.EXTERNAL_ACTIONS):
            raise ToolDenied("sync_agenda_to_calendar", Permission.EXTERNAL_ACTIONS)
        status = cal.status(ctx.state.guest_id)
        n = len(ctx.state.agenda)
        action = ProposedAction(
            tool="sync_agenda_to_calendar",
            args={},
            label="Sync to Google Calendar",
            description=f"Sync {_n(n, 'saved session')} to {status.calendar_name}",
        )
        card = Card(
            type="action",
            title="Please confirm",
            detail=f"{_n(n, 'saved session')} → “{status.calendar_name}”. Sessions you removed "
            "are taken off the calendar; nothing else in your calendar is touched.",
            action=action,
        )
        return AgentReply(
            intent="calendar_sync",
            reply=f"Sync {_n(n, 'saved session')} to your Google Calendar "
            f"“{status.calendar_name}”?",
            cards=[card],
        )

    def _recommend(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        day = self._day(ctx, req)
        hits: list[SessionHit] = call(
            "recommend_sessions", {"day": day.isoformat() if day else None, "max_sessions": 6}
        )
        if not hits:
            return AgentReply(
                intent="recommend",
                reply="Tell me what you're working on and what you want to learn, and I'll "
                "recommend sessions. For example: “I run Kubernetes for AI inference.”",
            )
        return AgentReply(
            intent="recommend",
            cards=_offer([_session_card(h) for h in hits]),
            reply=f"My top pick is “{hits[0].session.title}”. "
            f"Here are {_n(len(hits), 'session')} that match your goals.",
        )

    def _target(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> SessionHit | None:
        if req.context_session_id and re.search(r"\b(this|it)\b", req.message, re.I):
            hit: SessionHit = call("get_session_details", {"session_id": req.context_session_id})
            return hit
        query = _ADD_SCAFFOLD.sub("", req.message).strip(' .?!"“”')
        if len(query) < 3:
            return None
        hits: list[SessionHit] = call("search_sessions", {"query": query, "limit": 1})
        return hits[0] if hits else None

    def _ask(self, ctx: ToolContext, req: AgentChatRequest, call: Call) -> AgentReply:
        """Open questions: the grounded RAG answerer (cites records; never acts)."""
        personal = ctx.state.agent.allows(Permission.PERSONALIZATION)
        res = self.assistant.chat(
            ctx.rm,
            ctx.conf,
            ChatRequest(
                message=req.message,
                history=req.history,
                context_session_id=req.context_session_id,
            ),
            ctx.state if personal else None,
        )
        saved = {i.session_id for i in ctx.state.agenda}
        cards = _offer(
            [Card(type="session", session=s, in_agenda=s.id in saved) for s in res.sessions]
        )
        cards += [Card(type="speaker", speaker=p) for p in res.speakers]
        return AgentReply(
            intent="ask",
            reply=res.answer,
            cards=cards,
            mode=res.mode,
            citations=res.citations,
            generated_by=res.generated_by,
            trace=[ToolTrace(tool="grounded_answer", status="ok", detail=topic_query(req.message))],
        )


def _conflict_cards(view: AgendaView) -> list[Card]:
    return [
        Card(
            type="conflict",
            title="Time conflict",
            detail=f"{' and '.join(c.titles)} overlap by {c.overlap_minutes} minutes.",
        )
        for c in view.conflicts
    ]


_DENIED = {
    Permission.READ: "Enable your agent to let it search this event.",
    Permission.PERSONALIZATION: "I need permission to use your interests and goals for that. "
    "You can allow it in your agent's permissions.",
    Permission.AGENDA: "I need permission to manage your agenda for that. You can allow it in "
    "your agent's permissions; I'll still ask before every change.",
    Permission.INTEGRATIONS: "Connect your Google Calendar first: open Permissions, allow "
    "“Connect external accounts” and choose Connect Google Calendar.",
    Permission.EXTERNAL_ACTIONS: "I need permission to act in your Google Calendar. Allow "
    "“Act outside conCompass” in your agent's permissions; I'll still ask before each sync.",
}
