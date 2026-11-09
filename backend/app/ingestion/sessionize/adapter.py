"""Sessionize -> canonical model adapter."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.config.conferences import ConferenceConfig
from app.config.settings import get_settings
from app.domain.models import Provenance, Resource, Room, Session, Speaker, TimeSlot
from app.ingestion.base import NormalizedSource, SourcePayload, SourceValidationError
from app.ingestion.sessionize.schema import RawAllView, RawSession, RawSpeaker
from app.normalization.text import clean_text, strip_emoji

SOURCE_SYSTEM = "sessionize"
_PANEL = re.compile(r"\bpanel\b", re.IGNORECASE)
_WORKSHOP = re.compile(r"\b(workshop|hands-on lab)\b", re.IGNORECASE)
# Plausibility floor: refuse refreshes that look truncated (relative to a sane minimum).
MIN_SESSIONS = 10


def _hash(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _parse_json(raw: bytes, label: str) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceValidationError(f"{label}: not valid UTF-8 JSON ({exc})") from exc


class SessionizeAdapter:
    name = SOURCE_SYSTEM

    def __init__(self, min_sessions: int = MIN_SESSIONS) -> None:
        self.min_sessions = min_sessions

    # ---- loading -------------------------------------------------------------------------
    def load_local(self, conference: ConferenceConfig) -> SourcePayload:
        root = get_settings().repo_root
        s_path = root / conference.source.local_sessions_file
        p_path = root / conference.source.local_speakers_file
        for p in (s_path, p_path):
            if not p.exists():
                raise SourceValidationError(f"Local source file not found: {p}")
        mtime = datetime.fromtimestamp(Path(s_path).stat().st_mtime).astimezone()
        return SourcePayload(
            sessions_raw=s_path.read_bytes(),
            speakers_raw=p_path.read_bytes(),
            origin="local_file",
            retrieved_at=mtime,
            locations=(str(s_path), str(p_path)),
        )

    def fetch_remote(self, conference: ConferenceConfig) -> SourcePayload:
        headers = {"User-Agent": "KubeCompass-ingest/0.1", "Accept": "application/json"}
        with httpx.Client(timeout=30.0, headers=headers, follow_redirects=True) as client:
            s = client.get(conference.source.sessions_url)
            p = client.get(conference.source.speakers_url)
        for resp in (s, p):
            if resp.status_code != 200:
                raise SourceValidationError(f"{resp.url} returned HTTP {resp.status_code}")
        return SourcePayload(
            sessions_raw=s.content,
            speakers_raw=p.content,
            origin="remote",
            retrieved_at=datetime.now().astimezone(),
            locations=(conference.source.sessions_url, conference.source.speakers_url),
        )

    # ---- validation ----------------------------------------------------------------------
    def validate(self, payload: SourcePayload) -> tuple[RawAllView, list[RawSpeaker]]:
        all_json = _parse_json(payload.sessions_raw, "sessions payload")
        spk_json = _parse_json(payload.speakers_raw, "speakers payload")
        try:
            view = RawAllView.model_validate(all_json)
            if not isinstance(spk_json, list):
                raise TypeError("speakers payload must be a JSON array")
            speakers = [RawSpeaker.model_validate(s) for s in spk_json]
        except (ValidationError, TypeError) as exc:
            raise SourceValidationError(
                f"Sessionize payload failed schema validation: {exc}"
            ) from exc
        if len(view.sessions) < self.min_sessions:
            raise SourceValidationError(
                f"Only {len(view.sessions)} sessions in payload; refusing (min {self.min_sessions})"
            )
        return view, speakers

    # ---- normalization -------------------------------------------------------------------
    def normalize(
        self,
        payload: SourcePayload,
        conference: ConferenceConfig,
        ingested_at: datetime,
        ingestion_version: str,
    ) -> NormalizedSource:
        view, speakers_view = self.validate(payload)
        issues: list[str] = []
        rejected: list[dict[str, str]] = []
        cid = conference.id
        source_url = conference.source.sessions_url

        # Lookups built from the payload itself, keyed by *titles* configured per conference.
        q_by_title = {q.question: q.id for q in view.questions}
        cat_by_title = {c.title: c for c in view.categories}
        item_to_cat: dict[int, tuple[str, str]] = {
            i.id: (c.title, i.name) for c in view.categories for i in c.items
        }
        missing_cats = [
            t
            for t in [
                conference.categories.track,
                conference.categories.audience_level,
                conference.categories.subtopic,
                conference.categories.projects,
            ]
            if t and t not in cat_by_title
        ]
        if missing_cats:
            issues.append(f"Configured categories absent from source: {missing_cats}")

        def qid(title: str | None) -> int | None:
            return q_by_title.get(title) if title else None

        rooms = {r.id: _room(r.id, r.name) for r in view.rooms}

        # Speakers: /view/All is primary; /view/Speakers is cross-checked.
        spk_view_by_id = {s.id: s for s in speakers_view}
        if len(spk_view_by_id) != len(view.speakers):
            issues.append(
                f"Speaker count mismatch: All view {len(view.speakers)}, "
                f"Speakers view {len(spk_view_by_id)}"
            )
        q = conference.questions
        speakers: dict[str, Speaker] = {}
        for rsp in view.speakers:
            if rsp.id in speakers:
                rejected.append({"type": "speaker", "id": rsp.id, "reason": "duplicate id"})
                continue
            answers = {a.questionId: (a.answerValue or "").strip() for a in rsp.questionAnswers}
            company = answers.get(qid(q.speaker_company_override) or -1) or answers.get(
                qid(q.speaker_company) or -1
            )
            alt = spk_view_by_id.get(rsp.id)
            if alt is not None and sorted(s.id for s in alt.sessions) != sorted(rsp.sessions):
                issues.append(f"Speaker {rsp.id}: session refs differ between views")
            speakers[rsp.id] = Speaker(
                id=f"{cid}:{rsp.id}",
                conference_id=cid,
                source_id=rsp.id,
                full_name=rsp.fullName.strip(),
                first_name=rsp.firstName,
                last_name=rsp.lastName,
                tagline=clean_text(rsp.tagLine),
                bio=clean_text(rsp.bio),
                company=company or None,
                job_title=answers.get(qid(q.speaker_title) or -1) or None,
                photo_url=rsp.profilePicture,
                is_top_speaker=rsp.isTopSpeaker,
                links=[
                    Resource(
                        kind=(link.linkType or "other").lower(), url=link.url, title=link.title
                    )
                    for link in rsp.links
                    if link.url.startswith(("http://", "https://"))
                ],
                session_ids=[f"{cid}:{sid}" for sid in rsp.sessions],
                provenance=Provenance(
                    source_system=SOURCE_SYSTEM,
                    source_id=rsp.id,
                    source_url=conference.source.speakers_url,
                    ingested_at=ingested_at,
                    ingestion_version=ingestion_version,
                    payload_hash=_hash(rsp.model_dump()),
                ),
            )

        sessions: dict[str, Session] = {}
        seen_slot: dict[tuple[str, str | None, int | None], str] = {}
        for raw in view.sessions:
            if raw.id in sessions:
                rejected.append({"type": "session", "id": raw.id, "reason": "duplicate id"})
                continue
            slot_key = (raw.title.strip().lower(), raw.startsAt, raw.roomId)
            if slot_key in seen_slot:
                rejected.append(
                    {
                        "type": "session",
                        "id": raw.id,
                        "reason": f"duplicate of {seen_slot[slot_key]} (same title, time, room)",
                    }
                )
                continue
            seen_slot[slot_key] = raw.id
            sessions[raw.id] = self._session(
                raw,
                conference,
                item_to_cat,
                q_by_title,
                rooms,
                speakers,
                ingested_at,
                ingestion_version,
                source_url,
                issues,
            )

        recurring = [t for t, c in Counter(s.title for s in sessions.values()).items() if c > 1]
        if recurring:
            issues.append(
                f"{len(recurring)} titles appear in multiple distinct sessions (recurring slots), "
                "kept as separate sessions"
            )
        dangling = [
            (s.source_id, sp)
            for s in sessions.values()
            for sp in s.speaker_ids
            if sp.split(":", 1)[1] not in speakers
        ]
        if dangling:
            issues.append(f"{len(dangling)} session->speaker references point to unknown speakers")

        tracks = sorted({s.track for s in sessions.values() if s.track})
        return NormalizedSource(
            sessions=list(sessions.values()),
            speakers=list(speakers.values()),
            rooms=list(rooms.values()),
            tracks=tracks,
            issues=issues,
            rejected=rejected,
        )

    def _session(
        self,
        raw: RawSession,
        conference: ConferenceConfig,
        item_to_cat: dict[int, tuple[str, str]],
        q_by_title: dict[str, int],
        rooms: dict[int, Room],
        speakers: dict[str, Speaker],
        ingested_at: datetime,
        ingestion_version: str,
        source_url: str,
        issues: list[str],
    ) -> Session:
        cid = conference.id
        cats = conference.categories
        track: str | None = None
        level: str | None = None
        subtopics: list[str] = []
        projects: list[str] = []
        flags: list[str] = []
        for item_id in raw.categoryItems:
            if item_id not in item_to_cat:
                issues.append(f"Session {raw.id}: unknown category item {item_id}")
                continue
            title, name = item_to_cat[item_id]
            if title == cats.track:
                if track is not None:
                    issues.append(f"Session {raw.id}: multiple tracks; kept '{track}'")
                else:
                    track = strip_emoji(name)
            elif title == cats.audience_level:
                level = name
            elif title == cats.subtopic:
                subtopics.append(name)
            elif title == cats.projects:
                projects.append(name)
            elif title in cats.flags:
                flags.append(cats.flags[title])

        fmt, fmt_origin = _classify_format(raw, track, subtopics, conference)

        answers = {a.questionId: (a.answerValue or "").strip() for a in raw.questionAnswers}
        resources: list[Resource] = []
        q = conference.questions
        for kind, question in [
            ("slides", q.session_slides),
            ("repository", q.session_repository),
            ("demo", q.session_demo),
            ("website", q.session_website),
            ("location_map", q.session_location_map),
        ]:
            val: str | None = answers.get(q_by_title.get(question, -1)) if question else None
            if val and val.startswith(("http://", "https://")):
                resources.append(Resource(kind=kind, url=val, title=question))
        for kind, url in (("recording", raw.recordingUrl), ("livestream", raw.liveUrl)):
            if url:
                resources.append(Resource(kind=kind, url=url))

        time = _timeslot(raw, conference, issues)
        speaker_ids = [f"{cid}:{s}" for s in raw.speakers]
        names = [speakers[s].full_name for s in raw.speakers if s in speakers]
        room = rooms.get(raw.roomId) if raw.roomId is not None else None
        if raw.roomId is not None and room is None:
            issues.append(f"Session {raw.id}: unknown room {raw.roomId}")

        return Session(
            id=f"{cid}:{raw.id}",
            conference_id=cid,
            source_id=raw.id,
            title=raw.title.strip(),
            description=clean_text(raw.description),
            track=track,
            subtopics=subtopics,
            audience_level=level,
            format=fmt,
            format_origin=fmt_origin,
            flags=flags,
            project_tags=projects,
            speaker_ids=speaker_ids,
            speaker_names=names,
            time=time,
            room=room,
            resources=resources,
            status=raw.status,
            is_content=fmt not in conference.non_content_formats,
            provenance=Provenance(
                source_system=SOURCE_SYSTEM,
                source_id=raw.id,
                source_url=source_url,
                ingested_at=ingested_at,
                ingestion_version=ingestion_version,
                payload_hash=_hash(raw.model_dump()),
            ),
        )


def _room(room_id: int, name: str) -> Room:
    clean = name.strip()
    parts = [p.strip() for p in clean.split("|")]
    venue = parts[0] if len(parts) > 1 else None
    return Room(id=str(room_id), name=clean, venue=venue)


def _classify_format(
    raw: RawSession, track: str | None, subtopics: list[str], conference: ConferenceConfig
) -> tuple[str, str]:
    if not raw.speakers:
        for rule in conference.format_by_title_without_speakers:
            if re.search(rule.pattern, raw.title, re.IGNORECASE):
                return rule.format, "title_pattern"
    for st in subtopics:
        if st in conference.format_by_subtopic:
            return conference.format_by_subtopic[st], "subtopic"
    if track and track in conference.format_by_track:
        return conference.format_by_track[track], "category"
    if _PANEL.search(raw.title):
        return "panel", "title_pattern"
    if _WORKSHOP.search(raw.title):
        return "workshop", "title_pattern"
    return ("talk", "default") if raw.speakers else ("other", "default")


def _timeslot(raw: RawSession, conference: ConferenceConfig, issues: list[str]) -> TimeSlot | None:
    if not raw.startsAt or not raw.endsAt:
        issues.append(f"Session {raw.id}: missing start/end time")
        return None
    try:
        start_naive = datetime.fromisoformat(raw.startsAt)
        end_naive = datetime.fromisoformat(raw.endsAt)
    except ValueError:
        issues.append(f"Session {raw.id}: unparseable time {raw.startsAt!r}/{raw.endsAt!r}")
        return None
    if start_naive.tzinfo is not None:
        # Source already carries an offset; convert into the conference zone.
        start = start_naive.astimezone(conference.tz)
        end = end_naive.astimezone(conference.tz)
    else:
        # Sessionize returns wall-clock times in the event's local zone.
        start = start_naive.replace(tzinfo=conference.tz)
        end = end_naive.replace(tzinfo=conference.tz)
    if end <= start:
        issues.append(f"Session {raw.id}: end time not after start time")
        return None
    return TimeSlot(
        starts_at_local=raw.startsAt,
        ends_at_local=raw.endsAt,
        starts_at=start,
        ends_at=end,
        timezone=conference.timezone,
        day=start.date().isoformat(),
        duration_minutes=int((end - start).total_seconds() // 60),
    )
