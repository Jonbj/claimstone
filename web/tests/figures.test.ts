import { describe, expect, it } from "vitest";
import { figures, hostsFor, queryCount } from "@/lib/figures";

describe("figures", () => {
  const topics = [{ terms: ["a", "b", "c"] }, { terms: ["d"] }];
  it("query count is every term of every topic times the distinct sources", () => {
    expect(queryCount(topics, ["openalex", "crossref", "openalex"])).toBe(8);
    expect(queryCount([], ["openalex"])).toBe(0);
  });
  it("the ceiling is searches x requests each x rounds", () => {
    expect(figures({ topics, apis: ["openalex", "crossref"], maxRequestsEach: 3, rounds: 4 })).toEqual({
      searchesPerRound: 8, searchesTotal: 32, requestsPerRound: 24, requestsTotal: 96, minUnitsEach: 8 });
  });
  it("hosts follow the sources, sorted and unique", () => {
    expect(hostsFor(["crossref", "openalex", "openalex"])).toEqual(["api.crossref.org", "api.openalex.org"]);
  });
});
