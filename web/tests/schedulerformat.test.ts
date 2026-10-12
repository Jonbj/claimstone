import { describe, expect, it } from "vitest";
import { identityName, percent, ratio, requestsLine, utcRange } from "@/components/scheduler/format";
import { stateLabelKey } from "@/components/scheduler/labels";
import { CATALOGS } from "@/lib/i18n";
import { roundsOf } from "@/lib/scheduler";

describe("utcRange", () => {
  it("prints both ends in UTC with an arrow", () => {
    expect(utcRange("2026-11-01T00:00:00+00:00", "2026-11-30T12:30:00+00:00"))
      .toBe("1 Nov 2026, 00:00 UTC → 30 Nov 2026, 12:30 UTC");
  });
  it("converts a non-UTC offset to UTC", () => {
    expect(utcRange("2026-11-01T01:00:00+02:00", "2026-11-02T00:00:00Z"))
      .toBe("31 Oct 2026, 23:00 UTC → 2 Nov 2026, 00:00 UTC");
  });
  it("returns what it cannot parse as received", () => {
    expect(utcRange("soon", "later")).toBe("soon → later");
  });
});

describe("requestsLine", () => {
  it("is count times each equals total", () => {
    expect(requestsLine(3, 10, 30)).toBe("10 × 3 = 30");
  });
});

describe("ratio", () => {
  it("keeps the denominator", () => expect(ratio(3, 8)).toBe("3 / 8"));
  it("shows a dash for an unknown part", () => expect(ratio(null, 8)).toBe("— / 8"));
});

describe("identityName", () => {
  it("prefers the name, falls back to the operator, never invents", () => {
    expect(identityName({ name: "Bea", operator: "bea" })).toBe("Bea");
    expect(identityName({ operator: "bea" })).toBe("bea");
    expect(identityName({})).toBe("");
    expect(identityName(null)).toBe("");
    expect(identityName(undefined)).toBe("");
  });
});

describe("stateLabelKey", () => {
  it.each(["PLANNED", "AUTHORIZED", "REVOKED", "ENABLED", "DISABLED", "ALIVE", "STALE",
           "STOPPED", "NOT_STARTED", "UNKNOWN", "IDLE", "DRIVING", "INSUFFICIENT_ACQUISITION",
           "WAITING_FOR_SCHEDULE", "WAITING_FOR_EVIDENCE", "READY_FOR_HUMAN_READING"])(
    "%s has a key present in both catalogs", (word) => {
      const key = stateLabelKey(word);
      expect(key).toBe(`sched.state.${word}`);
      expect(CATALOGS.en[key!]).toBeTruthy();
      expect(CATALOGS.it[key!]).toBeTruthy();
    });
  it("returns null for an unknown word, never a default", () => {
    expect(stateLabelKey("SOMETHING_NEW")).toBeNull();
    expect(stateLabelKey("")).toBeNull();
    expect(stateLabelKey("authorized")).toBeNull();
  });
});

describe("roundsOf", () => {
  it("reads audit.rounds and tolerates a missing or malformed audit", () => {
    expect(roundsOf({ rounds: [{ round: "r1" }] })).toHaveLength(1);
    expect(roundsOf({})).toEqual([]);
    expect(roundsOf({ rounds: "no" })).toEqual([]);
    expect(roundsOf(null)).toEqual([]);
  });
});

describe("percent", () => {
  it("is a dash for anything that is not a number, never NaN", () => {
    expect(percent(null)).toBe("—");
    expect(percent(undefined)).toBe("—");
    expect(percent(Number.NaN)).toBe("—");
    expect(percent("0.5" as unknown as number)).toBe("—");
  });
  it("is one decimal", () => {
    expect(percent(0.375)).toBe("37.5%");
    expect(percent(0)).toBe("0.0%");
  });
});
