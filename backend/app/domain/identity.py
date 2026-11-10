"""Personal identity without accounts: an email or username becomes a stable attendee id.

The handle is normalized and turned into a UUID with HMAC-SHA256 under a server secret, so the
same handle reaches the same profile and agenda from any device. The handle itself is never
stored or logged; Elasticsearch only ever sees the derived id. There is no password, so this is
personalization, not authentication: anyone who types the same handle sees the same agenda.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from typing import Literal

# Used only when KUBECOMPASS_IDENTITY_SECRET is unset (local development).
_DEV_SECRET = b"kubecompass-dev-identity-secret"

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")

HandleKind = Literal["email", "username"]


class InvalidHandle(ValueError):
    pass


def normalize_handle(raw: str) -> tuple[str, HandleKind]:
    handle = raw.strip().lower()
    if "@" in handle:
        if len(handle) > 254 or not EMAIL_RE.match(handle):
            raise InvalidHandle("That doesn't look like a valid email address.")
        return handle, "email"
    if not USERNAME_RE.match(handle):
        raise InvalidHandle(
            "Usernames are 3–32 characters: letters, numbers, dots, dashes or underscores, "
            "starting with a letter or number."
        )
    return handle, "username"


def attendee_id_for(handle: str, secret: bytes | None) -> str:
    """Stable, non-reversible UUID for a normalized handle."""
    digest = hmac.new(secret or _DEV_SECRET, handle.encode("utf-8"), hashlib.sha256).digest()
    return str(uuid.UUID(bytes=digest[:16], version=4))


def masked(handle: str, kind: HandleKind) -> str:
    """What the UI shows back, e.g. 'al•••@gmail.com'."""
    if kind == "username":
        return handle
    local, _, domain = handle.partition("@")
    return f"{local[:2]}{'•' * 3}@{domain}"
