# Google Calendar integration

Lets an attendee connect Google Calendar to their event agent and sync saved sessions. It unlocks
the agent permissions **Connect external accounts** (once the server is configured) and **Act
outside conCompass** (once the attendee has connected a calendar).

## What it does
| Step | Behavior |
|---|---|
| Connect | OAuth 2.0 web flow. Scopes: `calendar.events` and `calendar.calendarlist.readonly` only. The `state` is HMAC-signed and expires after 10 minutes |
| Store | Refresh and access tokens are encrypted at rest (Fernet; key derived from `KUBECOMPASS_IDENTITY_SECRET`) and never sent to the browser or logged |
| Choose | Any calendar the user can write to (default: primary) |
| Sync | Only after the attendee confirms (agent card or **Sync my agenda now**). Deterministic event ids mean repeat syncs never duplicate; changed sessions are updated, removed ones deleted, unchanged ones skipped; 429/5xx retried with backoff; remaining failures reported and retried next time |
| Disconnect | Revokes the token at Google and deletes it here. If the user revokes access from their Google account, the next sync detects it and asks them to reconnect |

Code: `backend/app/integrations/google_calendar.py`, `backend/app/api/routes_integrations.py`,
`frontend/components/agent/calendar-section.tsx`. Tests: `backend/tests/unit/test_google_calendar.py`
(fake Google, no network).

## Setup (one-time, by the deployment owner)
1. Go to [Google Cloud Console](https://console.cloud.google.com/) and select or create a project.
2. **APIs & Services → Library**: enable **Google Calendar API**.
3. **APIs & Services → OAuth consent screen** (Google Auth Platform):
   - User type **External**; app name `conCompass`; support and developer contact email.
   - **Data access / Scopes**: add `.../auth/calendar.events` and
     `.../auth/calendar.calendarlist.readonly`.
   - **Audience**: while the app is in *Testing*, add the Google accounts that may connect as
     **test users** (up to 100). Anyone else sees "access blocked" until the app is published
     (calendar scopes are *sensitive*, so publishing to everyone requires Google's verification).
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type **Web application**.
   - **Authorized redirect URI**: `https://kubecompass.onrender.com/api/integrations/google/callback`
     (for local testing also `http://localhost:7860/api/integrations/google/callback`).
   - Copy the **Client ID** and **Client secret**.
5. Set on the host (Render → service → **Environment**), then save to redeploy:
   - `KUBECOMPASS_GOOGLE_CLIENT_ID` = the client ID
   - `KUBECOMPASS_GOOGLE_CLIENT_SECRET` = the client secret
   - `KUBECOMPASS_PUBLIC_BASE_URL` = `https://kubecompass.onrender.com` (no trailing slash)
   `KUBECOMPASS_IDENTITY_SECRET` must already be set and stay unchanged: it also encrypts tokens.
6. Open **My Agent → Permissions**. "Connect external accounts" is now available, and the Google
   Calendar section shows **Connect Google Calendar**.
