"""The attendee's event agent: settings and permissions, chat, confirmed actions, memory."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.agenda.store import AttendeeState
from app.agent.permissions import (
    CATALOG,
    AgentSettings,
    AuditEntry,
    Permission,
    PermissionInfo,
    normalize_grant,
)
from app.agent.service import AgentChatRequest, AgentReply, Card
from app.agent.tools import ToolContext, ToolDenied, ToolError, execute_confirmed
from app.api.deps import AttendeeDep, ConferenceDep, ContainerDep, ReadModelDep, rate_limit
from app.config.conferences import ConferenceConfig
from app.knowledge_graph.store import ConferenceReadModel
from app.services.container import Container

router = APIRouter(prefix="/api/agent")


class AgentStatus(BaseModel):
    conference_id: str
    enabled: bool
    permissions: list[Permission]
    enabled_at: datetime | None
    catalog: list[PermissionInfo]
    has_profile: bool
    audit: list[AuditEntry]


class AgentSettingsIn(BaseModel):
    enabled: bool
    permissions: list[Permission] = Field(default_factory=list)


class ActionIn(BaseModel):
    tool: str = Field(min_length=1, max_length=80)
    args: dict[str, str] = Field(default_factory=dict)
    confirmed: bool = Field(description="Must be true: the attendee confirmed this action")


def _status(conf_id: str, state: AttendeeState) -> AgentStatus:
    a = state.agent
    return AgentStatus(
        conference_id=conf_id,
        enabled=a.enabled,
        permissions=a.permissions if a.enabled else [],
        enabled_at=a.enabled_at,
        catalog=CATALOG,
        has_profile=state.profile is not None,
        audit=list(reversed(a.audit))[:20],
    )


def _context(
    container: Container,
    rm: ConferenceReadModel,
    conf: ConferenceConfig,
    state: AttendeeState,
    now: datetime | None = None,
) -> ToolContext:
    return ToolContext(
        rm=rm,
        conf=conf,
        state=state,
        now=(now or datetime.now(UTC)).astimezone(UTC),
        search=container.search,
        graph=container.graph,
        recommendations=container.recommendations,
        agenda=container.agenda,
    )


def _require_enabled(state: AttendeeState) -> None:
    if not state.agent.enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "agent_disabled",
                "message": "Enable your event agent and choose what it may do first.",
            },
        )


@router.get("", response_model=AgentStatus)
def get_agent(conf: ConferenceDep, state: AttendeeDep) -> AgentStatus:
    return _status(conf.id, state)


@router.put("", response_model=AgentStatus)
def update_agent(
    body: AgentSettingsIn, container: ContainerDep, conf: ConferenceDep, state: AttendeeDep
) -> AgentStatus:
    """Enable/disable the agent for this event and set its permissions (revocable any time)."""
    if body.enabled:
        was_enabled = state.agent.enabled
        state.agent.enabled = True
        state.agent.permissions = normalize_grant(body.permissions)
        state.agent.enabled_at = state.agent.enabled_at if was_enabled else datetime.now(UTC)
    else:  # disabling revokes everything; the audit trail is kept for the attendee to review
        state.agent = AgentSettings(audit=state.agent.audit)
    state = container.attendees.save(state)
    return _status(conf.id, state)


@router.delete("/memory", response_model=AgentStatus)
def clear_memory(container: ContainerDep, conf: ConferenceDep, state: AttendeeDep) -> AgentStatus:
    """Forget the interests, goals and preferences for this event (agenda is kept)."""
    state.profile = None
    state = container.attendees.save(state)
    return _status(conf.id, state)


@router.post("/chat", response_model=AgentReply, dependencies=[Depends(rate_limit)])
def chat(
    body: AgentChatRequest,
    container: ContainerDep,
    conf: ConferenceDep,
    rm: ReadModelDep,
    state: AttendeeDep,
) -> AgentReply:
    _require_enabled(state)
    ctx = _context(container, rm, conf, state, body.now)
    return container.agent.handle(ctx, body)


@router.post("/actions", response_model=AgentReply, dependencies=[Depends(rate_limit)])
def run_action(
    body: ActionIn,
    container: ContainerDep,
    conf: ConferenceDep,
    rm: ReadModelDep,
    state: AttendeeDep,
) -> AgentReply:
    """Execute a proposed action after the attendee confirmed it (re-checks permissions)."""
    _require_enabled(state)
    if not body.confirmed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "not_confirmed", "message": "Confirm the action to run it."},
        )
    ctx = _context(container, rm, conf, state)
    try:
        result = execute_confirmed(ctx, body.tool, dict(body.args))
    except ToolDenied as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_required",
                "message": f"Allow '{exc.permission.value}' in your agent's permissions first.",
            },
        ) from exc
    except ToolError as exc:
        container.attendees.save(ctx.state)  # keep the audit entry of the failed attempt
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    container.attendees.save(ctx.state)  # persists the audit entry (agenda already saved)
    return AgentReply(
        reply=result.message,
        intent="add" if body.tool == "add_session_to_agenda" else "remove",
        cards=[
            Card(
                type="session",
                session=result.session,
                in_agenda=body.tool == "add_session_to_agenda",
                badge="Saved" if body.tool == "add_session_to_agenda" else None,
            )
        ],
    )
