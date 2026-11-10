// Who is using KubeCompass in this browser.
//
// - Personal: the visitor entered an email or username; the server turned it into a stable
//   attendee id (the handle itself is never stored server-side). Same handle = same profile and
//   agenda on any device. Kept in localStorage until they sign out.
// - Guest: no handle entered. A random id that lives only in
//   this tab (sessionStorage), so nothing carries over to the next visit or the next person.
// - Unknown: nothing entered yet; a tab-only guest id is created on first use.

export type Identity =
  | { status: "personal"; attendeeId: string; kind: "email" | "username"; display: string }
  | { status: "guest"; attendeeId: string }
  | { status: "unknown" };

const PERSONAL_KEY = "kubecompass.identity";
const GUEST_KEY = "kubecompass.session-guest";
const LEGACY_KEY = "kubecompass.guest-id"; // shared-per-browser id from before identities

const UNKNOWN: Identity = { status: "unknown" };
let cached: Identity | null = null;
let fallbackId: string | null = null; // storage blocked (private mode): per page load
const listeners = new Set<() => void>();

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function read(): Identity {
  if (typeof window === "undefined") return UNKNOWN;
  try {
    window.localStorage.removeItem(LEGACY_KEY);
    const raw = window.localStorage.getItem(PERSONAL_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (p?.attendeeId && p?.display && (p.kind === "email" || p.kind === "username")) {
        return { status: "personal", attendeeId: p.attendeeId, kind: p.kind, display: p.display };
      }
    }
    const guest = window.sessionStorage.getItem(GUEST_KEY);
    if (guest) return { status: "guest", attendeeId: guest };
  } catch {
    if (fallbackId) return { status: "guest", attendeeId: fallbackId };
  }
  return UNKNOWN;
}

function emit(next: Identity) {
  cached = next;
  listeners.forEach((l) => l());
}

export function getIdentity(): Identity {
  return (cached ??= read());
}

export function getServerIdentity(): Identity {
  return UNKNOWN;
}

export function subscribeIdentity(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Attendee id sent as X-Guest-Id: the personal id, else a guest id for this tab only. */
export function getGuestId(): string {
  const id = getIdentity();
  if (id.status !== "unknown") return id.attendeeId;
  const guest = (fallbackId ??= uuid());
  try {
    window.sessionStorage.setItem(GUEST_KEY, guest);
  } catch {
    /* storage blocked: guest id lasts for this page load */
  }
  cached = { status: "guest", attendeeId: guest };
  return guest;
}

export function signInPersonal(p: { attendeeId: string; kind: "email" | "username"; display: string }) {
  try {
    window.localStorage.setItem(PERSONAL_KEY, JSON.stringify(p));
    window.sessionStorage.removeItem(GUEST_KEY);
  } catch {
    /* storage blocked: identity lasts for this page load */
  }
  emit({ status: "personal", ...p });
}

/** Forget the identity in this browser (the saved profile/agenda stay with the handle). */
export function signOut() {
  try {
    window.localStorage.removeItem(PERSONAL_KEY);
    window.sessionStorage.removeItem(GUEST_KEY);
  } catch {
    /* storage blocked */
  }
  fallbackId = null;
  cached = null;
  emit(read()); // a fresh tab-only guest is created on the next request
}
