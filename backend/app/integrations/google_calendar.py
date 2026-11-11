"""Google Calendar: OAuth connection, calendar choice and idempotent agenda sync.

Security
- Only two scopes: `calendar.events` (write events) and `calendar.calendarlist.readonly` (list
  calendars to choose from). No access to other Google data.
- Tokens are encrypted at rest (Fernet; key derived from the server's identity secret) and never
  returned to the browser or logged.
- The OAuth `state` is HMAC-signed, names the attendee and event, and expires after 10 minutes.
- Disconnecting revokes the token at Google and deletes the stored record.

Sync
- Each saved session maps to a deterministic Google event id, so repeating a sync never
  duplicates events (insert → 409 → update). Changed sessions are updated, removed ones deleted,
  unchanged ones skipped (content hash). Transient Google errors (429/5xx) are retried with backoff;
  items that still fail are reported and retried by the next sync.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field

from app.agenda.scheduling import Slot
from app.agenda.service import SEATING_NOTICE
from app.agenda.store import AttendeeState, AttendeeStore
from app.config.conferences import ConferenceConfig
from app.config.settings import Settings
from app.knowledge_graph.store import ConferenceReadModel

log = logging.getLogger(__name__)

PROVIDER = "google"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3"
STATE_TTL = 600
_DEV_SECRET = b"kubecompass-dev-identity-secret"


class CalendarError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---- models ------------------------------------------------------------------------------------
class SyncRecord(BaseModel):
    event_id: str
    content_hash: str
    calendar_id: str
    synced_at: datetime


class SyncSummary(BaseModel):
    at: datetime
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    failed: int = 0
    failures: list[str] = Field(default_factory=list)  # session titles
    error: str | None = None  # Google's reason for failures, in plain language

    @property
    def message(self) -> str:
        parts = [
            f"{n} {w}"
            for n, w in (
                (self.created, "added"),
                (self.updated, "updated"),
                (self.deleted, "removed"),
                (self.unchanged, "already up to date"),
            )
            if n
        ]
        text = "Google Calendar: " + (", ".join(parts) if parts else "nothing to sync") + "."
        if self.failed:
            text += f" {self.failed} couldn't be synced"
            text += f": {self.error}" if self.error else "."
            text += " Syncing again will retry them."
        return text


class CalendarConnection(BaseModel):
    connected_at: datetime
    scopes: list[str]
    refresh_token_enc: str
    access_token_enc: str | None = None
    access_expires_at: datetime | None = None
    calendar_id: str = "primary"
    calendar_name: str = "Primary calendar"
    synced: dict[str, SyncRecord] = Field(default_factory=dict)  # "<conference>:<session>"
    last_sync: SyncSummary | None = None


class CalendarStatus(BaseModel):
    configured: bool
    connected: bool
    calendar_id: str | None = None
    calendar_name: str | None = None
    last_sync: SyncSummary | None = None
    synced_sessions: int = 0


class CalendarOption(BaseModel):
    id: str
    name: str
    primary: bool = False


# ---- crypto / state ----------------------------------------------------------------------------
def server_secret(settings: Settings) -> bytes:
    s = settings.identity_secret
    return s.get_secret_value().encode() if s else _DEV_SECRET


class TokenCipher:
    def __init__(self, secret: bytes) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(b"concompass-tokens:" + secret).digest())
        self._f = Fernet(key)

    def seal(self, value: str) -> str:
        return self._f.encrypt(value.encode()).decode()

    def open(self, value: str) -> str:
        try:
            return self._f.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise CalendarError("reconnect", "Please reconnect Google Calendar.") from exc


def sign_state(secret: bytes, payload: dict[str, Any], now: float | None = None) -> str:
    body = dict(payload, exp=int((now or time.time()) + STATE_TTL))
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
    sig = hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_state(secret: bytes, state: str, now: float | None = None) -> dict[str, Any]:
    raw, _, sig = state.partition(".")
    good = hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()
    if not sig or not hmac.compare_digest(sig, good):
        raise CalendarError(
            "bad_state", "The Google sign-in link is invalid. Try connecting again."
        )
    body: dict[str, Any] = json.loads(base64.urlsafe_b64decode(raw.encode()))
    if body.get("exp", 0) < (now or time.time()):
        raise CalendarError("expired_state", "The Google sign-in took too long. Try again.")
    return body


def event_id(conference_id: str, session_id: str, guest_id: str) -> str:
    """Deterministic Google event id (base32hex alphabet a–v, 0–9; 5–1024 chars)."""
    digest = hashlib.sha256(f"{conference_id}|{session_id}|{guest_id}".encode()).digest()
    return "cc" + base64.b32hexencode(digest).decode().lower().rstrip("=")


# ---- Google HTTP -------------------------------------------------------------------------------
_REASONS = {
    "accessNotConfigured": "the Google Calendar API isn't enabled in the Google Cloud project. "
    "Enable it under APIs & Services → Library → Google Calendar API, then sync again.",
    "SERVICE_DISABLED": "the Google Calendar API isn't enabled in the Google Cloud project. "
    "Enable it under APIs & Services → Library → Google Calendar API, then sync again.",
    "insufficientPermissions": "Google didn't grant calendar access. Disconnect, connect again "
    "and tick the calendar checkbox on Google's screen.",
    "ACCESS_TOKEN_SCOPE_INSUFFICIENT": "Google didn't grant calendar access. Disconnect, connect "
    "again and tick the calendar checkbox on Google's screen.",
    "requiredAccessLevel": "you can't write to that calendar. Choose another one.",
    "notFound": "that calendar wasn't found. Choose another one.",
    "rateLimitExceeded": "Google is rate-limiting requests. Try again in a minute.",
    "quotaExceeded": "the Google project's daily quota is used up. Try again tomorrow.",
}


def google_reason(resp: httpx.Response) -> str:
    """Plain-language reason from a Google API error (status codes and reasons only)."""
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    if not isinstance(err, dict):
        err = {}
    codes = [str(e.get("reason", "")) for e in err.get("errors", []) if isinstance(e, dict)]
    codes += [str(err.get("status", ""))]
    codes += [str(d.get("reason", "")) for d in err.get("details", []) if isinstance(d, dict)]
    for c in codes:
        if c in _REASONS:
            return _REASONS[c]
    msg = str(err.get("message") or "")[:160]
    return f"Google answered {resp.status_code}" + (f" ({msg})" if msg else "") + "."


@dataclass
class GoogleHttp:
    """Thin client with retries; `transport` lets tests replace Google."""

    transport: httpx.BaseTransport | None = None
    timeout: float = 15.0
    backoff: tuple[float, ...] = (0.5, 1.5)

    def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
            for attempt in range(len(self.backoff) + 1):
                try:
                    resp = client.request(method, url, **kw)
                except httpx.TransportError as exc:
                    if attempt == len(self.backoff):
                        raise CalendarError("unreachable", "Couldn't reach Google.") from exc
                else:
                    if resp.status_code not in (429, 500, 502, 503, 504):
                        return resp
                    if attempt == len(self.backoff):
                        return resp
                time.sleep(self.backoff[attempt])
        raise CalendarError("unreachable", "Couldn't reach Google.")  # pragma: no cover


class GoogleCalendarService:
    def __init__(self, settings: Settings, store: AttendeeStore, http: GoogleHttp | None = None):
        self.settings = settings
        self.store = store
        self.http = http or GoogleHttp()
        self.cipher = TokenCipher(server_secret(settings))

    # ---- connection ----------------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return self.settings.google_configured

    @property
    def redirect_uri(self) -> str:
        return (
            f"{(self.settings.public_base_url or '').rstrip('/')}/api/integrations/google/callback"
        )

    def _require_configured(self) -> None:
        if not self.configured:
            raise CalendarError(
                "not_configured", "Google Calendar isn't set up on this server yet."
            )

    def authorization_url(self, guest_id: str, conference_id: str) -> str:
        self._require_configured()
        state = sign_state(server_secret(self.settings), {"g": guest_id, "c": conference_id})
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",  # always returns a refresh token
            "include_granted_scopes": "false",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def complete(self, code: str, state: str) -> tuple[str, str]:
        """OAuth callback: verify state, exchange the code, store encrypted tokens."""
        self._require_configured()
        body = verify_state(server_secret(self.settings), state)
        secret = self.settings.google_client_secret
        resp = self.http.request(
            "POST",
            TOKEN_URL,
            data={
                "code": code,
                "client_id": self.settings.google_client_id,
                "client_secret": secret.get_secret_value() if secret else "",
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            # Google's error code only (e.g. redirect_uri_mismatch, invalid_client); no secrets.
            log.warning(
                "google token exchange failed: %s %s",
                resp.status_code,
                (
                    resp.json()
                    if resp.headers.get("content-type", "").startswith("application/json")
                    else {}
                ).get("error"),
            )
            raise CalendarError("exchange_failed", "Google didn't accept the sign-in. Try again.")
        tok = resp.json()
        granted = set(str(tok.get("scope", "")).split())
        if SCOPES[0] not in granted:
            raise CalendarError(
                "scope_denied", "Calendar access wasn't granted, so nothing was connected."
            )
        if not tok.get("refresh_token"):
            raise CalendarError("exchange_failed", "Google didn't return a long-lived token.")
        conn = CalendarConnection(
            connected_at=datetime.now(UTC),
            scopes=sorted(granted),
            refresh_token_enc=self.cipher.seal(tok["refresh_token"]),
            access_token_enc=self.cipher.seal(tok["access_token"]),
            access_expires_at=datetime.now(UTC) + timedelta(seconds=int(tok.get("expires_in", 0))),
        )
        self._save(body["g"], conn)
        return body["g"], body["c"]

    def _load(self, guest_id: str) -> CalendarConnection | None:
        raw = self.store.load_integration(PROVIDER, guest_id)
        return CalendarConnection.model_validate(raw) if raw else None

    def _save(self, guest_id: str, conn: CalendarConnection) -> None:
        self.store.save_integration(PROVIDER, guest_id, conn.model_dump(mode="json"))

    def status(self, guest_id: str) -> CalendarStatus:
        conn = self._load(guest_id) if self.configured else None
        return CalendarStatus(
            configured=self.configured,
            connected=conn is not None,
            calendar_id=conn.calendar_id if conn else None,
            calendar_name=conn.calendar_name if conn else None,
            last_sync=conn.last_sync if conn else None,
            synced_sessions=len(conn.synced) if conn else 0,
        )

    def connected(self, guest_id: str) -> bool:
        return self.configured and self._load(guest_id) is not None

    def disconnect(self, guest_id: str) -> None:
        conn = self._load(guest_id)
        if conn is None:
            return
        try:  # revoke at Google; delete locally even if Google is unreachable
            token = self.cipher.open(conn.refresh_token_enc)
            self.http.request("POST", REVOKE_URL, params={"token": token})
        except CalendarError as exc:
            log.warning("Google token revocation failed: %s", exc.code)
        self.store.delete_integration(PROVIDER, guest_id)

    def _token(self, guest_id: str, conn: CalendarConnection) -> str:
        now = datetime.now(UTC)
        if (
            conn.access_token_enc
            and conn.access_expires_at
            and conn.access_expires_at > now + timedelta(seconds=60)
        ):
            return self.cipher.open(conn.access_token_enc)
        secret = self.settings.google_client_secret
        resp = self.http.request(
            "POST",
            TOKEN_URL,
            data={
                "client_id": self.settings.google_client_id,
                "client_secret": secret.get_secret_value() if secret else "",
                "refresh_token": self.cipher.open(conn.refresh_token_enc),
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code in (400, 401):  # revoked by the user at Google
            self.store.delete_integration(PROVIDER, guest_id)
            raise CalendarError("reconnect", "Google Calendar access was revoked. Connect again.")
        if resp.status_code != 200:
            raise CalendarError(
                "unreachable", "Google is not responding right now. Try again soon."
            )
        tok = resp.json()
        conn.access_token_enc = self.cipher.seal(tok["access_token"])
        conn.access_expires_at = now + timedelta(seconds=int(tok.get("expires_in", 0)))
        self._save(guest_id, conn)
        return str(tok["access_token"])

    def _conn(self, guest_id: str) -> CalendarConnection:
        self._require_configured()
        conn = self._load(guest_id)
        if conn is None:
            raise CalendarError("not_connected", "Connect Google Calendar first.")
        return conn

    # ---- calendars -----------------------------------------------------------------------------
    def calendars(self, guest_id: str) -> list[CalendarOption]:
        conn = self._conn(guest_id)
        token = self._token(guest_id, conn)
        resp = self.http.request(
            "GET",
            f"{API}/users/me/calendarList",
            params={"minAccessRole": "writer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            reason = google_reason(resp)
            log.warning("google calendarList failed: %s %s", resp.status_code, reason)
            raise CalendarError("google_error", f"Couldn't load your calendars: {reason}")
        return [
            CalendarOption(
                id=c["id"],
                name=c.get("summaryOverride") or c.get("summary") or c["id"],
                primary=bool(c.get("primary")),
            )
            for c in resp.json().get("items", [])
        ]

    def choose_calendar(self, guest_id: str, calendar_id: str) -> CalendarStatus:
        conn = self._conn(guest_id)
        match = next((c for c in self.calendars(guest_id) if c.id == calendar_id), None)
        if match is None:
            raise CalendarError("unknown_calendar", "That calendar isn't writable for you.")
        conn = self._conn(guest_id)  # reload: token refresh may have saved it
        conn.calendar_id, conn.calendar_name = match.id, match.name
        self._save(guest_id, conn)
        return self.status(guest_id)

    # ---- sync ----------------------------------------------------------------------------------
    def _event(
        self, rm: ConferenceReadModel, conf: ConferenceConfig, sid: str
    ) -> dict[str, Any] | None:
        doc = rm.sessions.get(sid)
        slot = Slot.from_doc(doc) if doc else None
        if doc is None or slot is None:
            return None
        speakers = ", ".join(doc.get("speaker_names", []))
        description = "\n".join(
            x
            for x in (
                f"Speakers: {speakers}" if speakers else "",
                f"Track: {doc['track']}" if doc.get("track") else "",
                (doc.get("description") or "")[:1500],
                f"Official schedule: {conf.source.schedule_url}"
                if conf.source.schedule_url
                else "",
                SEATING_NOTICE,
                "Added by conCompass.",
            )
            if x
        )
        local = slot.start.astimezone(conf.tz), slot.end.astimezone(conf.tz)
        return {
            "summary": doc["title"],
            "location": slot.room or "",
            "description": description,
            "start": {"dateTime": local[0].isoformat(), "timeZone": conf.timezone},
            "end": {"dateTime": local[1].isoformat(), "timeZone": conf.timezone},
            "status": "confirmed",
            "extendedProperties": {"private": {"concompass_session": sid}},
            **(
                {"source": {"title": conf.short_name, "url": conf.source.schedule_url}}
                if conf.source.schedule_url
                else {}
            ),
        }

    def sync(
        self, rm: ConferenceReadModel, conf: ConferenceConfig, state: AttendeeState
    ) -> SyncSummary:
        guest = state.guest_id
        conn = self._conn(guest)
        token = self._token(guest, conn)
        conn = self._conn(guest)
        headers = {"Authorization": f"Bearer {token}"}
        cal = quote(conn.calendar_id, safe="")
        summary = SyncSummary(at=datetime.now(UTC))
        prefix = f"{conf.id}:"
        wanted = {i.session_id for i in state.agenda}

        for sid in sorted(wanted):
            body = self._event(rm, conf, sid)
            if body is None:
                continue
            key = prefix + sid
            eid = event_id(conf.id, sid, guest)
            digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            prev = conn.synced.get(key)
            if prev and prev.content_hash == digest and prev.calendar_id == conn.calendar_id:
                summary.unchanged += 1
                continue
            resp = self.http.request(
                "POST", f"{API}/calendars/{cal}/events", json={**body, "id": eid}, headers=headers
            )
            kind = "created"
            if resp.status_code == 409:  # exists (or was deleted by the user): update in place
                resp = self.http.request(
                    "PUT", f"{API}/calendars/{cal}/events/{eid}", json=body, headers=headers
                )
                kind = "updated"
            if resp.status_code not in (200, 201):
                summary.failed += 1
                summary.failures.append(str(body["summary"]))
                summary.error = summary.error or google_reason(resp)
                log.warning("google event write failed: %s %s", resp.status_code, summary.error)
                continue
            setattr(summary, kind, getattr(summary, kind) + 1)
            conn.synced[key] = SyncRecord(
                event_id=eid,
                content_hash=digest,
                calendar_id=conn.calendar_id,
                synced_at=summary.at,
            )

        for key in [
            k for k in conn.synced if k.startswith(prefix) and k[len(prefix) :] not in wanted
        ]:
            rec = conn.synced[key]
            resp = self.http.request(
                "DELETE",
                f"{API}/calendars/{quote(rec.calendar_id, safe='')}/events/{rec.event_id}",
                headers=headers,
            )
            if resp.status_code in (200, 204, 404, 410):
                summary.deleted += 1
                del conn.synced[key]
            else:
                summary.failed += 1
                summary.error = summary.error or google_reason(resp)

        conn.last_sync = summary
        self._save(guest, conn)
        return summary
