import { formatDay, formatTime, formatTimeRange, tzAbbrev } from "@/lib/format";
import { sanitizeHighlight } from "@/components/sessions/session-card";
import { shortRoom } from "@/components/sessions/session-parts";

describe("conference-time formatting", () => {
  it("renders times in the conference zone, not the viewer's", () => {
    // 18:00 UTC on Nov 10 2026 is 11:00 MST in Salt Lake City.
    expect(formatTime("2026-11-10T18:00:00Z", "America/Denver")).toBe("11:00 AM");
    expect(formatTimeRange("2026-11-10T11:00:00-07:00", "2026-11-10T11:30:00-07:00", "America/Denver")).toBe("11:00 AM – 11:30 AM");
    expect(tzAbbrev("2026-11-10T18:00:00Z", "America/Denver")).toBe("MST");
  });
  it("never shifts conference-local dates", () => {
    expect(formatDay("2026-11-10")).toBe("Tue, Nov 10");
  });
  it("labels missing times honestly", () => {
    expect(formatTime(null, "America/Denver")).toBe("Time TBA");
  });
});

describe("highlight sanitizing", () => {
  it("keeps <mark> but escapes everything else", () => {
    const out = sanitizeHighlight('<mark>GPU</mark> <img src=x onerror=alert(1)>');
    expect(out).toContain("<mark>GPU</mark>");
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img");
  });
});

describe("room labels", () => {
  it("shortens venue | level | room", () => {
    expect(shortRoom("Salt Palace | Level 2 | 250 A-C")).toBe("250 A-C · Salt Palace L2");
    expect(shortRoom("Room TBD")).toBe("Room TBD");
  });
});
