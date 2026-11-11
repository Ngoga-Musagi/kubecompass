"""Google Calendar connection: connect (OAuth), choose a calendar, disconnect (revokes)."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.agenda.store import AttendeeState
from app.agent.permissions import Permission
from app.api.deps import AttendeeDep, ContainerDep, rate_limit
from app.integrations.google_calendar import (
    CalendarError,
    CalendarOption,
    CalendarStatus,
    server_secret,
    verify_state,
)

router = APIRouter(prefix="/api/integrations/google")
log = logging.getLogger(__name__)


class ConnectOut(BaseModel):
    auth_url: str


class CalendarChoice(BaseModel):
    calendar_id: str = Field(min_length=1, max_length=300)


def _http(exc: CalendarError) -> HTTPException:
    code = status.HTTP_409_CONFLICT if exc.code == "not_connected" else status.HTTP_502_BAD_GATEWAY
    if exc.code == "not_configured":
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HTTPException(code, detail={"code": exc.code, "message": exc.message})


def _require_integrations(state: AttendeeState) -> None:
    if not state.agent.allows(Permission.INTEGRATIONS):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_required",
                "message": "Allow “Connect external accounts” in your agent's permissions first.",
            },
        )


@router.get("", response_model=CalendarStatus)
def calendar_status(container: ContainerDep, state: AttendeeDep) -> CalendarStatus:
    return container.calendar.status(state.guest_id)


@router.post("/connect", response_model=ConnectOut, dependencies=[Depends(rate_limit)])
def connect(container: ContainerDep, state: AttendeeDep) -> ConnectOut:
    _require_integrations(state)
    try:
        return ConnectOut(
            auth_url=container.calendar.authorization_url(state.guest_id, state.conference_id)
        )
    except CalendarError as exc:
        raise _http(exc) from exc


@router.get("/callback", include_in_schema=False)
def callback(
    container: ContainerDep,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Google redirects the browser here; the signed state identifies the attendee."""
    base = (container.settings.public_base_url or "").rstrip("/")

    def back(**params: str) -> RedirectResponse:
        return RedirectResponse(f"{base}/agent?{urlencode(params)}", status_code=303)

    if error or not code:
        log.info("google callback: user did not grant access (%s)", error or "no code")
        return back(calendar="cancelled")
    try:
        body = verify_state(server_secret(container.settings), state)
        attendee = container.attendees.load(body["c"], body["g"])
        if not attendee.agent.allows(Permission.INTEGRATIONS):  # revoked while signing in
            log.warning("google callback: integrations permission missing")
            return back(calendar="error", reason="permission_required")
        container.calendar.complete(code, state)
    except CalendarError as exc:
        log.warning("google callback failed: %s", exc.code)
        return back(calendar="error", reason=exc.code)
    return back(calendar="connected")


@router.get("/calendars", response_model=list[CalendarOption])
def calendars(container: ContainerDep, state: AttendeeDep) -> list[CalendarOption]:
    _require_integrations(state)
    try:
        return container.calendar.calendars(state.guest_id)
    except CalendarError as exc:
        raise _http(exc) from exc


@router.put("/calendar", response_model=CalendarStatus)
def choose_calendar(
    body: CalendarChoice, container: ContainerDep, state: AttendeeDep
) -> CalendarStatus:
    _require_integrations(state)
    try:
        return container.calendar.choose_calendar(state.guest_id, body.calendar_id)
    except CalendarError as exc:
        raise _http(exc) from exc


@router.delete("", response_model=CalendarStatus)
def disconnect(container: ContainerDep, state: AttendeeDep) -> CalendarStatus:
    """Always allowed: revokes the token at Google and deletes it here."""
    container.calendar.disconnect(state.guest_id)
    if Permission.EXTERNAL_ACTIONS in state.agent.permissions:
        state.agent.permissions = [
            p for p in state.agent.permissions if p != Permission.EXTERNAL_ACTIONS
        ]
        container.attendees.save(state)
    return container.calendar.status(state.guest_id)
