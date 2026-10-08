import { describe, expect, it } from "vitest";
import { formatUtc } from "@/lib/datetime";

describe("J3.3: formatUtc", () => {
  it("formats in UTC whatever the offset", () => {
    expect(formatUtc("2026-10-06T20:41:46+00:00")).toBe("6 Oct 2026, 20:41 UTC");
    expect(formatUtc("2026-10-06T22:41:46+02:00")).toBe("6 Oct 2026, 20:41 UTC");
    expect(formatUtc("2026-01-01T00:00:00Z")).toBe("1 Jan 2026, 00:00 UTC");
  });
  it("returns anything unparseable or zone-less as received", () => {
    expect(formatUtc("yesterday")).toBe("yesterday");
    expect(formatUtc("2026-10-06T20:41:46")).toBe("2026-10-06T20:41:46");
    expect(formatUtc("2026-13-45T99:99:99+00:00")).toBe("2026-13-45T99:99:99+00:00");
  });
});
