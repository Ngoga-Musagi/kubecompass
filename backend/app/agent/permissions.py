"""What the attendee allows their event agent to do.

Permissions are stored per attendee *and per event* (the attendee document is event-scoped), are
off by default, and are checked by the tool executor on the server. The UI only displays them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

AUDIT_LIMIT = 50


class Permission(StrEnum):
    READ = "read"
    PERSONALIZATION = "personalization"
    AGENDA = "agenda"
    INTEGRATIONS = "integrations"
    EXTERNAL_ACTIONS = "external_actions"


class PermissionInfo(BaseModel):
    id: Permission
    title: str
    description: str
    available: bool = True  # False = shown but cannot be granted yet
    unavailable_reason: str | None = None


_BASE: list[PermissionInfo] = [
    PermissionInfo(
        id=Permission.READ,
        title="Read event information",
        description="Search this event's sessions, speakers, rooms and schedule, and answer "
        "questions about them. Always on while the agent is enabled.",
    ),
    PermissionInfo(
        id=Permission.PERSONALIZATION,
        title="Use my interests and goals",
        description="Use the interests, goals and preferences you give it to rank and explain "
        "recommendations. You can view, edit or clear them at any time.",
    ),
    PermissionInfo(
        id=Permission.AGENDA,
        title="Manage my agenda",
        description="Read your conCompass agenda, find conflicts and free time, and propose "
        "changes. Nothing is added or removed until you confirm each change.",
    ),
    PermissionInfo(
        id=Permission.INTEGRATIONS,
        title="Connect external accounts",
        description="Connect your Google Calendar and see which calendars you can write to. "
        "You can disconnect at any time; access is revoked at Google.",
    ),
    PermissionInfo(
        id=Permission.EXTERNAL_ACTIONS,
        title="Act outside conCompass",
        description="Add, update and remove your saved sessions in your connected Google "
        "Calendar, only when you confirm a sync.",
    ),
]


def catalog(calendar_configured: bool, calendar_connected: bool) -> list[PermissionInfo]:
    """Permission levels, with integration levels unlocked only when they can actually work."""
    out = []
    for p in _BASE:
        if p.id == Permission.INTEGRATIONS and not calendar_configured:
            p = p.model_copy(
                update={
                    "available": False,
                    "unavailable_reason": "Google Calendar isn't set up on this server yet.",
                }
            )
        elif p.id == Permission.EXTERNAL_ACTIONS and not calendar_connected:
            p = p.model_copy(
                update={
                    "available": False,
                    "unavailable_reason": "Connect Google Calendar first (in this panel).",
                }
            )
        out.append(p)
    return out


class AuditEntry(BaseModel):
    at: datetime
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    outcome: str  # done | already_done | failed
    detail: str | None = None


class AgentSettings(BaseModel):
    enabled: bool = False
    permissions: list[Permission] = Field(default_factory=list)
    enabled_at: datetime | None = None
    audit: list[AuditEntry] = Field(default_factory=list)

    def allows(self, permission: Permission) -> bool:
        return self.enabled and permission in self.permissions

    def record(self, entry: AuditEntry) -> None:
        self.audit = [*self.audit, entry][-AUDIT_LIMIT:]


def normalize_grant(
    requested: list[Permission], available: list[PermissionInfo]
) -> list[Permission]:
    """READ is implied by enabling the agent; unavailable permissions are never granted."""
    grantable = {p.id for p in available if p.available}
    granted = {Permission.READ, *(p for p in requested if p in grantable)}
    return [p for p in Permission if p in granted]
