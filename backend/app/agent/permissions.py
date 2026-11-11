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


CATALOG: list[PermissionInfo] = [
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
        description="Access services you connect, such as Google Calendar.",
        available=False,
        unavailable_reason="Coming with Google Calendar support.",
    ),
    PermissionInfo(
        id=Permission.EXTERNAL_ACTIONS,
        title="Act outside conCompass",
        description="Make changes in connected services, only within what you allow, and always "
        "with your confirmation.",
        available=False,
        unavailable_reason="Requires a connected account.",
    ),
]
GRANTABLE = {p.id for p in CATALOG if p.available}


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


def normalize_grant(requested: list[Permission]) -> list[Permission]:
    """READ is implied by enabling the agent; unavailable permissions are never granted."""
    granted = {Permission.READ, *(p for p in requested if p in GRANTABLE)}
    return [p for p in Permission if p in granted]
