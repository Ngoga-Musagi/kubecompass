from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.agenda.store import AttendeeState
from app.agent.permissions import AgentSettings, Permission, normalize_grant
from app.agent.service import classify, parse_day, parse_minutes
from app.agent.tools import TOOLS, ToolContext, ToolDenied, ToolError, execute_confirmed, run_tool


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("What session should I attend next?", "next_session"),
        ("Where is my next session?", "next_session"),
        ("I have 30 minutes free. What would you recommend?", "free_time"),
        ("got an hour to kill", "free_time"),
        ("What is happening in the next room?", "happening_now"),
        ("Build my agenda for Wednesday", "build_agenda"),
        ("plan my day tomorrow", "build_agenda"),
        ("Do I have any conflicts?", "conflicts"),
        ("Add the session about GPU time-slicing to my agenda", "add"),
        ("remove this from my agenda", "remove"),
        ("show my agenda", "show_agenda"),
        ("Find something related to GPU scheduling.", "ask"),
        ("Who is speaking about Kueue?", "ask"),
        ("What should I attend on Thursday?", "recommend"),
    ],
)
def test_intent_routing(message, intent):
    assert classify(message) == intent


def test_minutes_and_days():
    assert parse_minutes("I have 30 minutes free") == 30
    assert parse_minutes("got 2 hours") == 120
    assert parse_minutes("half an hour free") == 30
    assert parse_minutes("some free time") == 60
    now = datetime(2026, 11, 10, 9, 0, tzinfo=ZoneInfo("America/Denver"))
    days = [date(2026, 11, d) for d in range(8, 13)]
    assert parse_day("plan Wednesday", now, days) == date(2026, 11, 11)
    assert parse_day("what about nov 12", now, days) == date(2026, 11, 12)
    assert parse_day("tomorrow please", now, days) == date(2026, 11, 11)
    assert parse_day("plan my week", now, days) is None


def test_grants_imply_read_and_skip_unavailable():
    assert normalize_grant([]) == [Permission.READ]
    granted = normalize_grant([Permission.AGENDA, Permission.EXTERNAL_ACTIONS])
    assert granted == [Permission.READ, Permission.AGENDA]  # external actions not grantable yet
    assert not AgentSettings(permissions=[Permission.READ]).allows(Permission.READ)  # disabled


def _ctx(*perms: Permission) -> ToolContext:
    state = AttendeeState(conference_id="c", guest_id="g")
    state.agent = AgentSettings(enabled=True, permissions=list(perms))
    # Services are never reached when a permission check fails.
    return ToolContext(
        rm=None,
        conf=None,
        state=state,
        now=datetime.now(UTC),  # type: ignore[arg-type]
        search=None,
        graph=None,
        recommendations=None,
        agenda=None,
    )  # type: ignore[arg-type]


def test_tools_enforce_permissions_server_side():
    ctx = _ctx(Permission.READ)
    for name in ("next_session", "get_user_agenda", "recommend_sessions", "suggest_agenda"):
        with pytest.raises(ToolDenied):
            run_tool(ctx, name)
    with pytest.raises(ToolDenied):
        execute_confirmed(ctx, "add_session_to_agenda", {"session_id": "x"})


def test_consequential_tools_never_run_without_confirmation_path():
    ctx = _ctx(Permission.READ, Permission.AGENDA)
    with pytest.raises(ToolError) as exc:
        run_tool(ctx, "add_session_to_agenda", {"session_id": "x"})
    assert exc.value.code == "needs_confirmation"
    with pytest.raises(ToolError):  # read tools are not "actions"
        execute_confirmed(ctx, "search_sessions", {"query": "gpu"})
    assert {t.name for t in TOOLS.values() if t.consequential} == {
        "add_session_to_agenda",
        "remove_session_from_agenda",
    }


def test_spoken_time_and_place_are_natural():
    from app.agent.service import _when, _where
    from app.schemas.api import SessionSummary

    s = SessionSummary(
        id="c:1",
        conference_id="c",
        title="T",
        track=None,
        format="talk",
        audience_level=None,
        starts_at=datetime(2026, 11, 12, 13, 50, tzinfo=ZoneInfo("America/Denver")),
        ends_at=None,
        starts_at_local=None,
        day=None,
        duration_minutes=None,
        room="Hyatt Regency | Level 2 | Salt Lake Ballroom DE",
        venue="Hyatt Regency",
        speakers=[],
        topics=[],
        technologies=[],
        flags=[],
        is_content=True,
        has_resources=False,
    )
    assert _when(s) == "Thursday at 1:50 PM"
    assert _where(s) == "Salt Lake Ballroom DE, Hyatt Regency"
    assert _where(s.model_copy(update={"room": None, "venue": None})) == "a room not published yet"
