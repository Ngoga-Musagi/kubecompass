"""Google Calendar integration against a fake Google (no network)."""

import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import SecretStr

from app.agenda.store import AgendaItem, AttendeeState, SavedSnapshot
from app.config.settings import Settings
from app.integrations.google_calendar import (
    SCOPES,
    CalendarError,
    GoogleCalendarService,
    GoogleHttp,
    event_id,
    sign_state,
    verify_state,
)

GUEST = "11111111-2222-4333-8444-555555555555"


class MemoryStore:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], dict[str, Any]] = {}

    def load_integration(self, provider: str, guest: str) -> dict[str, Any] | None:
        return self.data.get((provider, guest))

    def save_integration(self, provider: str, guest: str, data: dict[str, Any]) -> None:
        self.data[(provider, guest)] = json.loads(json.dumps(data))

    def delete_integration(self, provider: str, guest: str) -> None:
        self.data.pop((provider, guest), None)


class FakeGoogle:
    """Token, calendarList and events endpoints with programmable failures."""

    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []
        self.fail_next: list[int] = []  # status codes to return before succeeding
        self.scope = " ".join(SCOPES)
        self.refresh_status = 200
        self.revoked: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(f"{req.method} {req.url.path}")
        if self.fail_next and req.url.host == "www.googleapis.com":
            return httpx.Response(self.fail_next.pop(0))
        if req.url.path == "/token":
            form = parse_qs(req.content.decode())
            if form["grant_type"] == ["refresh_token"]:
                if self.refresh_status != 200:
                    return httpx.Response(self.refresh_status, json={"error": "invalid_grant"})
                return httpx.Response(200, json={"access_token": "at-2", "expires_in": 3600})
            return httpx.Response(
                200,
                json={
                    "access_token": "at-1",
                    "refresh_token": "rt-secret",
                    "expires_in": 3600,
                    "scope": self.scope,
                },
            )
        if req.url.path == "/revoke":
            self.revoked.append(req.url.params["token"])
            return httpx.Response(200)
        if req.url.path.endswith("/calendarList"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "primary-id", "summary": "Me", "primary": True},
                        {"id": "team@group", "summary": "Team"},
                    ]
                },
            )
        m = re.match(r"/calendar/v3/calendars/([^/]+)/events(?:/([^/]+))?$", req.url.path)
        assert m, req.url.path
        eid = m.group(2)
        if req.method == "POST":
            body = json.loads(req.content)
            if body["id"] in self.events:
                return httpx.Response(409)
            self.events[body["id"]] = body
            return httpx.Response(200, json=body)
        if req.method == "PUT":
            self.events[eid] = json.loads(req.content)
            return httpx.Response(200, json=self.events[eid])
        if req.method == "DELETE":
            return httpx.Response(204 if self.events.pop(eid, None) else 410)
        raise AssertionError(req.method)


def _session(sid: str, title: str, start: datetime) -> dict[str, Any]:
    return {
        "id": sid,
        "title": title,
        "speaker_names": ["Ada"],
        "track": "AI",
        "description": "About things.",
        "room": {"name": "151", "venue": "Salt Palace"},
        "time": {
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=30)).isoformat(),
        },
    }


@pytest.fixture
def world():
    google = FakeGoogle()
    settings = Settings(
        google_client_id="cid",
        google_client_secret=SecretStr("csecret"),
        public_base_url="https://app.example",
        identity_secret=SecretStr("s" * 32),
    )
    store = MemoryStore()
    svc = GoogleCalendarService(
        settings, store, GoogleHttp(httpx.MockTransport(google), backoff=(0, 0))
    )  # type: ignore[arg-type]
    tz = ZoneInfo("America/Denver")
    t = datetime(2026, 11, 11, 10, 0, tzinfo=tz)
    rm = SimpleNamespace(
        sessions={
            "c:1": _session("c:1", "GPU sharing", t),
            "c:2": _session("c:2", "Kueue deep dive", t + timedelta(hours=1)),
        }
    )
    conf = SimpleNamespace(
        id="c",
        timezone="America/Denver",
        tz=tz,
        short_name="KubeCon",
        source=SimpleNamespace(schedule_url="https://example/schedule"),
    )
    snap = SavedSnapshot(title="x")
    state = AttendeeState(
        conference_id="c",
        guest_id=GUEST,
        agenda=[
            AgendaItem(session_id=s, added_at=datetime.now(UTC), snapshot=snap)
            for s in ("c:1", "c:2")
        ],
    )
    return SimpleNamespace(google=google, svc=svc, store=store, rm=rm, conf=conf, state=state)


def _connect(w) -> None:
    url = w.svc.authorization_url(GUEST, "c")
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == [" ".join(SCOPES)] and q["access_type"] == ["offline"]
    assert q["redirect_uri"] == ["https://app.example/api/integrations/google/callback"]
    assert w.svc.complete("auth-code", q["state"][0]) == (GUEST, "c")


def test_state_is_signed_and_expires():
    secret = b"k" * 32
    st = sign_state(secret, {"g": GUEST, "c": "c"}, now=1000)
    assert verify_state(secret, st, now=1001)["g"] == GUEST
    with pytest.raises(CalendarError, match="invalid"):
        verify_state(secret, st[:-1] + ("0" if st[-1] != "0" else "1"), now=1001)
    with pytest.raises(CalendarError) as exc:
        verify_state(secret, st, now=1000 + 601)
    assert exc.value.code == "expired_state"


def test_event_ids_are_deterministic_and_valid():
    a = event_id("c", "c:1", GUEST)
    assert a == event_id("c", "c:1", GUEST) != event_id("c", "c:2", GUEST)
    assert re.fullmatch(r"[a-v0-9]{5,1024}", a)


def test_connect_stores_tokens_encrypted(world):
    _connect(world)
    raw = json.dumps(list(world.store.data.values()))
    assert "rt-secret" not in raw and "at-1" not in raw  # encrypted at rest
    st = world.svc.status(GUEST)
    assert st.configured and st.connected and st.calendar_id == "primary"


def test_missing_calendar_scope_connects_nothing(world):
    world.google.scope = SCOPES[1]  # user unticked calendar access on Google's screen
    with pytest.raises(CalendarError) as exc:
        _connect(world)
    assert exc.value.code == "scope_denied" and not world.store.data


def test_sync_is_idempotent_and_tracks_changes(world):
    _connect(world)
    w = world
    first = w.svc.sync(w.rm, w.conf, w.state)
    assert (first.created, first.failed) == (2, 0) and len(w.google.events) == 2
    ev = w.google.events[event_id("c", "c:1", GUEST)]
    assert ev["start"]["timeZone"] == "America/Denver" and ev["location"] == "151"

    again = w.svc.sync(w.rm, w.conf, w.state)
    assert (again.created, again.updated, again.unchanged) == (0, 0, 2)  # no duplicates

    w.rm.sessions["c:1"]["room"] = {"name": "255", "venue": "Salt Palace"}  # schedule change
    w.state.agenda = [i for i in w.state.agenda if i.session_id == "c:1"]  # removed c:2
    changed = w.svc.sync(w.rm, w.conf, w.state)
    assert (changed.updated, changed.deleted) == (1, 1)
    assert list(w.google.events) == [event_id("c", "c:1", GUEST)]
    assert w.google.events[event_id("c", "c:1", GUEST)]["location"] == "255"


def test_existing_event_is_updated_not_duplicated(world):
    _connect(world)
    eid = event_id("c", "c:1", GUEST)
    world.google.events[eid] = {"id": eid, "summary": "stale"}  # e.g. sync record lost
    res = world.svc.sync(world.rm, world.conf, world.state)
    assert (res.created, res.updated) == (1, 1) and len(world.google.events) == 2


def test_transient_errors_are_retried_and_failures_reported(world):
    _connect(world)
    world.google.fail_next = [503, 429]  # first event: two transient errors, then success
    ok = world.svc.sync(world.rm, world.conf, world.state)
    assert (ok.created, ok.failed) == (2, 0)

    world.state.agenda.append(
        AgendaItem(session_id="c:3", added_at=datetime.now(UTC), snapshot=SavedSnapshot(title="x"))
    )
    world.rm.sessions["c:3"] = _session("c:3", "Flaky", datetime(2026, 11, 12, 9, tzinfo=UTC))
    world.google.fail_next = [500, 500, 500]  # persistent failure for c:3
    bad = world.svc.sync(world.rm, world.conf, world.state)
    assert bad.failed == 1 and bad.failures == ["Flaky"] and "retry" in bad.message
    retry = world.svc.sync(world.rm, world.conf, world.state)  # next sync retries it
    assert (retry.created, retry.failed) == (1, 0)


def test_expired_token_refreshes_and_revoked_access_disconnects(world):
    _connect(world)
    conn = world.store.data[("google", GUEST)]
    conn["access_expires_at"] = "2000-01-01T00:00:00Z"
    world.svc.sync(world.rm, world.conf, world.state)
    assert world.google.calls.count("POST /token") == 2  # code exchange + refresh before sync

    world.store.data[("google", GUEST)]["access_expires_at"] = "2000-01-01T00:00:00Z"
    world.google.refresh_status = 400  # user revoked access in their Google account
    with pytest.raises(CalendarError) as exc:
        world.svc.sync(world.rm, world.conf, world.state)
    assert exc.value.code == "reconnect" and not world.svc.status(GUEST).connected


def test_choose_calendar_and_disconnect_revokes(world):
    _connect(world)
    assert [c.name for c in world.svc.calendars(GUEST)] == ["Me", "Team"]
    assert world.svc.choose_calendar(GUEST, "team@group").calendar_name == "Team"
    with pytest.raises(CalendarError):
        world.svc.choose_calendar(GUEST, "someone-elses@group")
    world.svc.disconnect(GUEST)
    assert world.google.revoked == ["rt-secret"] and not world.svc.status(GUEST).connected


def test_unconfigured_server_offers_nothing():
    svc = GoogleCalendarService(Settings(google_client_id=None), MemoryStore())  # type: ignore[arg-type]
    assert svc.status(GUEST).configured is False
    with pytest.raises(CalendarError) as exc:
        svc.authorization_url(GUEST, "c")
    assert exc.value.code == "not_configured"


def test_autosync_needs_switch_permission_and_connection(world, monkeypatch):
    from app.agent.permissions import AgentSettings, Permission
    from app.integrations import autosync

    monkeypatch.setattr(autosync, "get_conference", lambda _cid: world.conf)
    container = SimpleNamespace(
        attendees=SimpleNamespace(load=lambda _c, _g: world.state),
        read_models=SimpleNamespace(get=lambda _c: world.rm),
        calendar=world.svc,
    )
    _connect(world)
    perms = [Permission.READ, Permission.INTEGRATIONS]
    world.state.agent = AgentSettings(enabled=True, permissions=perms, calendar_autosync=True)
    autosync.run_autosync(container, "c", GUEST)  # switch on but no external_actions → nothing
    assert world.google.events == {}

    world.state.agent.permissions = [*perms, Permission.EXTERNAL_ACTIONS]
    world.state.agent.calendar_autosync = False
    autosync.run_autosync(container, "c", GUEST)  # permission but switch off → nothing
    assert world.google.events == {}

    world.state.agent.calendar_autosync = True
    autosync.run_autosync(container, "c", GUEST)  # all three → both sessions synced
    assert len(world.google.events) == 2

    world.svc.disconnect(GUEST)
    world.state.agenda = world.state.agenda[:1]
    autosync.run_autosync(container, "c", GUEST)  # disconnected → no calls, no crash


def test_google_reasons_are_explained(world):
    _connect(world)
    disabled = {
        "error": {
            "code": 403,
            "status": "PERMISSION_DENIED",
            "message": "Google Calendar API has not been used in project 1 before",
            "errors": [{"reason": "accessNotConfigured"}],
        }
    }

    def api_disabled(req: httpx.Request) -> httpx.Response:
        if req.url.host == "www.googleapis.com":
            return httpx.Response(403, json=disabled)
        return world.google(req)

    world.svc.http = GoogleHttp(httpx.MockTransport(api_disabled), backoff=())
    res = world.svc.sync(world.rm, world.conf, world.state)
    assert res.failed == 2 and "Google Calendar API isn't enabled" in res.message
    with pytest.raises(CalendarError, match="isn't enabled"):
        world.svc.calendars(GUEST)
