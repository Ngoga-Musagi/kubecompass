// Guest identity: a random UUID kept in this browser. No account or personal data required.
const KEY = "kubecompass.guest-id";
let memoryId: string | null = null;

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  // RFC 4122 v4 fallback
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function getGuestId(): string {
  if (memoryId) return memoryId;
  try {
    const existing = window.localStorage.getItem(KEY);
    if (existing) return (memoryId = existing);
    const fresh = uuid();
    window.localStorage.setItem(KEY, fresh);
    return (memoryId = fresh);
  } catch {
    // Private mode / SSR: keep a per-session id in memory.
    return (memoryId = memoryId ?? uuid());
  }
}
