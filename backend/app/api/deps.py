"""Shared FastAPI dependencies: conference resolution, read model, guest identity, admin auth."""

from __future__ import annotations

import hmac
import re
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status

from app.agenda.store import AttendeeState
from app.config.conferences import ConferenceConfig, UnknownConferenceError, get_conference
from app.knowledge_graph.store import ConferenceReadModel
from app.services.container import Container, get_container

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

ContainerDep = Annotated[Container, Depends(get_container)]


def conference_dep(
    container: ContainerDep,
    conference: Annotated[str | None, Query(max_length=64, pattern=r"^[a-z0-9-]+$")] = None,
) -> ConferenceConfig:
    cid = conference or container.settings.default_conference_id
    try:
        return get_conference(cid)
    except UnknownConferenceError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "unknown_conference", "message": f"Unknown conference '{cid}'"},
        ) from exc


ConferenceDep = Annotated[ConferenceConfig, Depends(conference_dep)]


def read_model_dep(container: ContainerDep, conf: ConferenceDep) -> ConferenceReadModel:
    rm = container.read_models.get(conf.id)
    if rm is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "not_indexed",
                "message": "Conference data has not been ingested yet. Run `make ingest`.",
            },
        )
    return rm


ReadModelDep = Annotated[ConferenceReadModel, Depends(read_model_dep)]


def guest_id_dep(x_guest_id: Annotated[str | None, Header()] = None) -> str | None:
    if x_guest_id is None:
        return None
    gid = x_guest_id.strip().lower()
    if not _UUID.match(gid):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_guest_id", "message": "X-Guest-Id must be a UUID"},
        )
    return gid


def required_guest_dep(guest: Annotated[str | None, Depends(guest_id_dep)]) -> str:
    if guest is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "missing_guest_id", "message": "X-Guest-Id header is required"},
        )
    return guest


def attendee_dep(
    container: ContainerDep, conf: ConferenceDep, guest: Annotated[str, Depends(required_guest_dep)]
) -> AttendeeState:
    return container.attendees.load(conf.id, guest)


AttendeeDep = Annotated[AttendeeState, Depends(attendee_dep)]


def optional_attendee_dep(
    container: ContainerDep,
    conf: ConferenceDep,
    guest: Annotated[str | None, Depends(guest_id_dep)],
) -> AttendeeState | None:
    return container.attendees.load(conf.id, guest) if guest else None


OptionalAttendeeDep = Annotated[AttendeeState | None, Depends(optional_attendee_dep)]


def admin_dep(
    container: ContainerDep, authorization: Annotated[str | None, Header()] = None
) -> None:
    token = container.settings.admin_token
    if token is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_disabled",
                "message": "Admin operations are disabled (no admin token configured).",
            },
        )
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.get_secret_value().encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Invalid admin token"},
        )


class RateLimiter:
    """Small in-memory sliding-window limiter for expensive endpoints (per client IP)."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def __call__(self, request: Request, container: ContainerDep) -> None:
        limit = container.settings.rate_limit_per_minute
        key = f"{request.client.host if request.client else 'unknown'}:{request.url.path}"
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": "Too many requests; try again in a minute.",
                },
            )
        q.append(now)


rate_limit = RateLimiter()
