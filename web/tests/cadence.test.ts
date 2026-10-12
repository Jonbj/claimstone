import { describe, expect, it } from "vitest";
import { checkRounds, generateRounds } from "@/lib/cadence";

const NOW = new Date("2026-10-12T10:00:00Z");

describe("generateRounds", () => {
  it("monthly: four windows from the start date, each ending where the next begins", () => {
    const r = generateRounds({ kind: "monthly", start: "2026-11-01", count: 4 }, "Update");
    expect(r.map((x) => x.round)).toEqual(["update-2026-11", "update-2026-12", "update-2027-01", "update-2027-02"]);
    expect(r[0]).toMatchObject({ not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z", title: "Update 2026-11" });
    expect(r[3].expires_at).toBe("2027-03-01T00:00:00Z");
  });
  it("monthly from the 31st clamps to short months and never goes backwards", () => {
    const r = generateRounds({ kind: "monthly", start: "2026-12-31", count: 3 }, "Update");
    expect(r.map((x) => x.not_before)).toEqual(["2026-12-31T00:00:00Z", "2027-01-31T00:00:00Z", "2027-02-28T00:00:00Z"]);
    expect(r[2].expires_at).toBe("2027-03-31T00:00:00Z");
  });
  it("weekly and every-N-days step by whole days", () => {
    const w = generateRounds({ kind: "weekly", start: "2026-11-02", count: 2 }, "Update");
    expect(w[1].not_before).toBe("2026-11-09T00:00:00Z");
    const d = generateRounds({ kind: "days", start: "2026-11-02", every: 10, count: 2 }, "Update");
    expect(d[1].not_before).toBe("2026-11-12T00:00:00Z");
    expect(d[0].round).toBe("update-2026-11-02");
  });
  it("names are URL-safe whatever the title prefix", () => {
    const r = generateRounds({ kind: "weekly", start: "2026-11-02", count: 1 }, "Aggiornamento città");
    expect(r[0].round).toMatch(/^[A-Za-z0-9_-]+$/);
  });
});

describe("checkRounds (early messages; the server stays the authority)", () => {
  const ok = generateRounds({ kind: "monthly", start: "2026-11-01", count: 2 }, "Update");
  it("accepts a clean list", () => expect(checkRounds(ok, new Set(), NOW)).toEqual([]));
  it("flags a start in the past", () => {
    const bad = generateRounds({ kind: "monthly", start: "2026-10-01", count: 1 }, "Update");
    expect(checkRounds(bad, new Set(), NOW).map((p) => p.code)).toContain("PAST");
  });
  it("flags overlap, disorder, duplicate and known round names, and the 366-day limit", () => {
    const a = { round: "r1", title: "t", not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z" };
    const b = { round: "r1", title: "t", not_before: "2026-11-15T00:00:00Z", expires_at: "2026-12-15T00:00:00Z" };
    const codes = checkRounds([a, b], new Set(["r9"]), NOW).map((p) => p.code);
    expect(codes).toEqual(expect.arrayContaining(["OVERLAP", "DUPLICATE"]));
    expect(checkRounds([{ ...a, round: "r9" }], new Set(["r9"]), NOW).map((p) => p.code)).toContain("KNOWN");
    const far = { round: "far", title: "t", not_before: "2027-09-01T00:00:00Z", expires_at: "2027-11-15T00:00:00Z" };
    expect(checkRounds([far], new Set(), NOW).map((p) => p.code)).toContain("TOO_FAR");
  });
  it("flags 0 or more than 32 rounds, a bad name and an empty title", () => {
    expect(checkRounds([], new Set(), NOW).map((p) => p.code)).toContain("COUNT");
    const bad = { round: "has space", title: " ", not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z" };
    expect(checkRounds([bad], new Set(), NOW).map((p) => p.code)).toEqual(expect.arrayContaining(["NAME", "TITLE"]));
  });
});

describe("generateRounds, further cases", () => {
  it("a window ends where the next begins, so the generated list passes the early checks", () => {
    const r = generateRounds({ kind: "weekly", start: "2026-11-02", count: 5 }, "Update");
    r.slice(1).forEach((x, i) => expect(x.not_before).toBe(r[i].expires_at));
    expect(checkRounds(r, new Set(), NOW)).toEqual([]);
  });
  it("accents are folded in the round name and kept in the title", () => {
    const r = generateRounds({ kind: "weekly", start: "2026-11-02", count: 1 }, "Aggiornamento città");
    expect(r[0].round).toBe("aggiornamento-citta-2026-11-02");
    expect(r[0].title).toBe("Aggiornamento città 2026-11-02");
  });
  it("a window that ends before it starts is flagged", () => {
    const bad = { round: "r", title: "t", not_before: "2026-12-01T00:00:00Z", expires_at: "2026-11-01T00:00:00Z" };
    expect(checkRounds([bad], new Set(), NOW).map((p) => p.code)).toContain("WINDOW");
  });
  it("problems carry the row they belong to", () => {
    const a = { round: "r1", title: "t", not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z" };
    const b = { ...a, round: "bad name" };
    expect(checkRounds([a, b], new Set(), NOW)).toEqual([{ index: 1, code: "NAME" }, { index: 1, code: "ORDER" }]);
  });
});
