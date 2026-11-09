// All times are rendered in the conference's IANA zone (never the viewer's local zone).

/** `day` is already a conference-local YYYY-MM-DD; anchor at noon UTC so it never shifts. */
export function formatDay(day: string, style: "short" | "long" = "short"): string {
  const d = new Date(`${day}T12:00:00Z`);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    weekday: style === "long" ? "long" : "short",
    month: style === "long" ? "long" : "short",
    day: "numeric",
  }).format(d);
}

export function formatTime(iso: string | null | undefined, timeZone: string): string {
  if (!iso) return "Time TBA";
  return new Intl.DateTimeFormat("en-US", { timeZone, hour: "numeric", minute: "2-digit" }).format(
    new Date(iso),
  );
}

export function formatTimeRange(
  start: string | null | undefined,
  end: string | null | undefined,
  timeZone: string,
): string {
  if (!start) return "Time TBA";
  return end ? `${formatTime(start, timeZone)} – ${formatTime(end, timeZone)}` : formatTime(start, timeZone);
}

export function tzAbbrev(iso: string | null | undefined, timeZone: string): string {
  const d = iso ? new Date(iso) : new Date();
  const part = new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "short" })
    .formatToParts(d)
    .find((p) => p.type === "timeZoneName");
  return part?.value ?? timeZone;
}

export function formatDateRange(start: string | null, end: string | null): string {
  if (!start) return "";
  const s = new Date(`${start}T12:00:00Z`);
  const e = end ? new Date(`${end}T12:00:00Z`) : s;
  const month = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });
  const sameMonth = s.getUTCMonth() === e.getUTCMonth();
  return sameMonth
    ? `${month.format(s)} ${s.getUTCDate()}–${e.getUTCDate()}, ${e.getUTCFullYear()}`
    : `${month.format(s)} ${s.getUTCDate()} – ${month.format(e)} ${e.getUTCDate()}, ${e.getUTCFullYear()}`;
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.round(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

export const FORMAT_LABELS: Record<string, string> = {
  talk: "Talk",
  keynote: "Keynote",
  lightning_talk: "Lightning talk",
  tutorial: "Tutorial",
  demo: "Demo",
  panel: "Panel",
  workshop: "Workshop",
  contribfest: "ContribFest",
  poster: "Poster",
  birds_of_a_feather: "BoF",
  co_located: "Co-located event",
  community: "Community",
  tour: "Tour",
  expo: "Expo",
  break: "Break",
  logistics: "Logistics",
  other: "Session",
};

export const formatLabel = (f: string) => FORMAT_LABELS[f] ?? f.replace(/_/g, " ");

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

/** Session ids are "{conference}:{source}"; URLs only need the encoded id. */
export const sessionHref = (id: string) => `/sessions/${encodeURIComponent(id)}`;
export const speakerHref = (id: string) => `/speakers/${encodeURIComponent(id)}`;
export const entityHref = (id: string) => `/topics/${encodeURIComponent(id)}`;
