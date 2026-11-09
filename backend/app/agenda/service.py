"""Personal agenda: add/remove/reorder, conflicts, transitions, gaps, change notices,
alternatives and ICS export."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.agenda.scheduling import (
    Slot,
    conflicts_with,
    find_conflicts,
    find_gaps,
    find_tight_transitions,
)
from app.agenda.store import AgendaItem, AttendeeState, AttendeeStore, SavedSnapshot
from app.calendar.ics import CalendarEvent, build_ics
from app.config.conferences import ConferenceConfig
from app.knowledge_graph.service import GraphService
from app.knowledge_graph.store import ConferenceReadModel
from app.schemas.api import SessionSummary
from app.services.presenters import session_summary

SEATING_NOTICE = (
    "Saving a session to your agenda does not reserve a seat. Seating is subject to event "
    "policies, room capacity and availability."
)


class AgendaError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ChangeNotice(BaseModel):
    session_id: str
    title: str
    kind: str  # modified | removed
    fields: list[str] = Field(default_factory=list)
    before: dict[str, str | None] = Field(default_factory=dict)
    after: dict[str, str | None] = Field(default_factory=dict)


class AgendaEntry(BaseModel):
    session: SessionSummary
    added_at: datetime
    conflicts_with: list[str] = Field(default_factory=list)
    change: ChangeNotice | None = None
    position: int = 0


class ConflictOut(BaseModel):
    session_ids: list[str]
    titles: list[str]
    overlap_minutes: int


class TransitionOut(BaseModel):
    from_session_id: str
    to_session_id: str
    gap_minutes: int
    reason: str


class GapOut(BaseModel):
    day: str
    start: datetime
    end: datetime
    minutes: int


class AgendaDay(BaseModel):
    day: str
    entries: list[AgendaEntry]
    gaps: list[GapOut]


class AgendaView(BaseModel):
    conference_id: str
    timezone: str
    total: int
    days: list[AgendaDay]
    unscheduled: list[AgendaEntry]  # removed from source or missing times
    conflicts: list[ConflictOut]
    transitions: list[TransitionOut]
    notices: list[ChangeNotice]
    seating_notice: str = SEATING_NOTICE
    data_version: str


class Alternative(BaseModel):
    session: SessionSummary
    reason: str
    fits_agenda: bool
    origin: str


def _snapshot(doc: dict) -> SavedSnapshot:  # type: ignore[type-arg]
    t = doc.get("time") or {}
    return SavedSnapshot(
        title=doc["title"],
        starts_at_local=t.get("starts_at_local"),
        ends_at_local=t.get("ends_at_local"),
        room=(doc.get("room") or {}).get("name"),
    )


def _change(item: AgendaItem, doc: dict | None) -> ChangeNotice | None:  # type: ignore[type-arg]
    if doc is None:
        return ChangeNotice(session_id=item.session_id, title=item.snapshot.title, kind="removed")
    now = _snapshot(doc).model_dump()
    then = item.snapshot.model_dump()
    fields = [k for k in ("title", "starts_at_local", "ends_at_local", "room") if now[k] != then[k]]
    if not fields:
        return None
    return ChangeNotice(
        session_id=item.session_id,
        title=doc["title"],
        kind="modified",
        fields=fields,
        before={k: then[k] for k in fields},
        after={k: now[k] for k in fields},
    )


class AgendaService:
    def __init__(
        self,
        store: AttendeeStore,
        graph: GraphService,
        low_signal: frozenset[str] = frozenset(),
        alternative_min: float = 0.82,
    ) -> None:
        self.low_signal = low_signal
        self.alternative_min = alternative_min  # "similar abstract" cutoff, per embedding model
        self.store = store
        self.graph = graph

    # ---- mutations -----------------------------------------------------------------------
    def add(
        self,
        rm: ConferenceReadModel,
        state: AttendeeState,
        session_id: str,
        note: str | None = None,
    ) -> AttendeeState:
        doc = rm.sessions.get(session_id)
        if doc is None:
            raise AgendaError("unknown_session", f"Session {session_id} does not exist")
        if any(i.session_id == session_id for i in state.agenda):
            raise AgendaError("duplicate", "Session is already in your agenda")
        if len(state.agenda) >= 200:
            raise AgendaError("limit", "Agenda is limited to 200 sessions")
        state.agenda.append(
            AgendaItem(
                session_id=session_id,
                added_at=datetime.now(UTC),
                snapshot=_snapshot(doc),
                note=note,
                position=len(state.agenda),
            )
        )
        return self.store.save(state)

    def remove(self, state: AttendeeState, session_id: str) -> AttendeeState:
        before = len(state.agenda)
        state.agenda = [i for i in state.agenda if i.session_id != session_id]
        if len(state.agenda) == before:
            raise AgendaError("not_in_agenda", "Session is not in your agenda")
        return self.store.save(state)

    def reorder(self, state: AttendeeState, ordered_ids: list[str]) -> AttendeeState:
        pos = {sid: i for i, sid in enumerate(ordered_ids)}
        for item in state.agenda:
            item.position = pos.get(item.session_id, len(pos) + item.position)
        return self.store.save(state)

    def acknowledge_changes(self, rm: ConferenceReadModel, state: AttendeeState) -> AttendeeState:
        """Accept the current schedule for saved sessions (clears change notices)."""
        for item in state.agenda:
            doc = rm.sessions.get(item.session_id)
            if doc is not None:
                item.snapshot = _snapshot(doc)
        return self.store.save(state)

    # ---- views ---------------------------------------------------------------------------
    def view(
        self, rm: ConferenceReadModel, conf: ConferenceConfig, state: AttendeeState
    ) -> AgendaView:
        slots: list[Slot] = []
        entries: dict[str, AgendaEntry] = {}
        notices: list[ChangeNotice] = []
        unscheduled: list[AgendaEntry] = []
        for item in state.agenda:
            doc = rm.sessions.get(item.session_id)
            change = _change(item, doc)
            if change:
                notices.append(change)
            if doc is None:
                continue
            entry = AgendaEntry(
                session=session_summary(doc, rm.speakers),
                added_at=item.added_at,
                change=change,
                position=item.position,
            )
            slot = Slot.from_doc(doc)
            if slot is None:
                unscheduled.append(entry)
                continue
            slots.append(slot)
            entries[item.session_id] = entry
        conflicts = find_conflicts(slots)
        by_id = {s.session_id: s for s in slots}
        for c in conflicts:
            entries[c.a].conflicts_with.append(c.b)
            entries[c.b].conflicts_with.append(c.a)
        by_day: dict[str, list[AgendaEntry]] = defaultdict(list)
        for sid, e in entries.items():
            by_day[by_id[sid].start.astimezone(conf.tz).date().isoformat()].append(e)
        gaps_by_day: dict[str, list[GapOut]] = defaultdict(list)
        for g in find_gaps(slots):
            gaps_by_day[g.day].append(
                GapOut(day=g.day, start=g.start, end=g.end, minutes=g.minutes)
            )
        days = [
            AgendaDay(
                day=d,
                entries=sorted(es, key=lambda e: (e.session.starts_at, e.position)),
                gaps=gaps_by_day.get(d, []),
            )
            for d, es in sorted(by_day.items())
        ]
        return AgendaView(
            conference_id=rm.conference_id,
            timezone=conf.timezone,
            total=len(state.agenda),
            days=days,
            unscheduled=unscheduled,
            conflicts=[
                ConflictOut(
                    session_ids=[c.a, c.b],
                    titles=[by_id[c.a].title, by_id[c.b].title],
                    overlap_minutes=c.overlap_minutes,
                )
                for c in conflicts
            ],
            transitions=[
                TransitionOut(
                    from_session_id=t.from_id,
                    to_session_id=t.to_id,
                    gap_minutes=t.gap_minutes,
                    reason=t.reason,
                )
                for t in find_tight_transitions(slots)
            ],
            notices=notices,
            data_version=rm.version,
        )

    def alternatives(
        self, rm: ConferenceReadModel, state: AttendeeState, session_id: str, limit: int = 6
    ) -> list[Alternative]:
        """Similar sessions that would fit the rest of the agenda (to resolve conflicts)."""
        doc = rm.sessions.get(session_id)
        if doc is None:
            raise AgendaError("unknown_session", f"Session {session_id} does not exist")
        saved = {i.session_id for i in state.agenda}
        others = [
            s
            for s in (
                Slot.from_doc(rm.sessions[i]) for i in saved if i in rm.sessions and i != session_id
            )
            if s
        ]
        cands: dict[str, tuple[float, str, str]] = {}
        title = doc["title"].strip().lower()
        for sid, d in rm.sessions.items():  # recurring repeats of the same session
            if sid != session_id and d["title"].strip().lower() == title:
                cands[sid] = (3.0, "Same session at another time", "explicit")
        for r in self.graph.related_sessions(rm, session_id, limit=20):
            cands.setdefault(
                r.session.id, (1.0 + r.confidence, r.evidence or "Related content", r.origin)
            )
        vec = rm.vector(session_id)
        alt_min = self.alternative_min
        if vec is not None and rm.vectors is not None:
            sims = rm.vectors @ vec
            for idx in sims.argsort()[::-1][:30]:
                sid = rm.vector_ids[int(idx)]
                cos = float(sims[idx])
                if cos < alt_min:
                    break
                if sid != session_id and rm.sessions[sid].get("is_content", True):
                    cands.setdefault(
                        sid, (cos - 0.3, f"Similar abstract (similarity {cos:.2f})", "inferred")
                    )
        # Sessions sharing specific (non-generic) topics or technologies.
        mine = {
            e["id"]: e["name"] for e in doc.get("entities", []) if e["id"] not in self.low_signal
        }
        if mine:
            for sid, d in rm.sessions.items():
                if sid == session_id or sid in cands or not d.get("is_content", True):
                    continue
                shared = [mine[e["id"]] for e in d.get("entities", []) if e["id"] in mine]
                if len(shared) >= 2:
                    cands[sid] = (
                        0.2 + 0.1 * len(shared),
                        "Also covers " + ", ".join(shared[:3]),
                        "extracted",
                    )
        out: list[tuple[bool, float, Alternative]] = []
        for sid, (score, reason, origin) in cands.items():
            if sid in saved or sid not in rm.sessions:
                continue
            slot = Slot.from_doc(rm.sessions[sid])
            fits = slot is not None and not conflicts_with(slot, others)
            out.append(
                (
                    fits,
                    score,
                    Alternative(
                        session=session_summary(rm.sessions[sid], rm.speakers),
                        reason=reason,
                        fits_agenda=fits,
                        origin=origin,
                    ),
                )
            )
        out.sort(key=lambda x: (not x[0], -x[1]))
        return [a for _, _, a in out[:limit]]

    def free_fits(
        self, rm: ConferenceReadModel, state: AttendeeState, session_ids: list[str]
    ) -> list[str]:
        saved = {i.session_id for i in state.agenda}
        slots = [s for s in (Slot.from_doc(rm.sessions[i]) for i in saved if i in rm.sessions) if s]
        out = []
        for sid in session_ids:
            if sid in saved or sid not in rm.sessions:
                continue
            slot = Slot.from_doc(rm.sessions[sid])
            if slot is not None and not conflicts_with(slot, slots):
                out.append(sid)
        return out

    def export_ics(
        self, rm: ConferenceReadModel, conf: ConferenceConfig, state: AttendeeState
    ) -> str:
        events: list[CalendarEvent] = []
        for item in state.agenda:
            doc = rm.sessions.get(item.session_id)
            slot = Slot.from_doc(doc) if doc else None
            if doc is None or slot is None:
                continue
            speakers = ", ".join(doc.get("speaker_names", []))
            desc = "\n".join(
                filter(
                    None,
                    [
                        f"Speakers: {speakers}" if speakers else None,
                        f"Track: {doc['track']}" if doc.get("track") else None,
                        (doc.get("description") or "")[:1500] or None,
                        f"Source: {conf.source.adapter} session {doc['source_id']}",
                        SEATING_NOTICE,
                    ],
                )
            )
            events.append(
                CalendarEvent(
                    uid=f"{doc['id'].replace(':', '-')}@kubecompass",
                    title=doc["title"],
                    start=slot.start,
                    end=slot.end,
                    location=slot.room,
                    description=desc,
                    url=conf.source.schedule_url,
                )
            )
        return build_ics(events, conf.timezone, f"{conf.short_name} · KubeCompass agenda")
