// Finding a series' grants: one bounded walk at limit=100, then cheap refreshes by id.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { findSeriesGrants, refreshGrants } from "@/components/scheduler/grants";
import { setCsrfToken } from "@/lib/control";
import { err, indexPage, json, mandate, OTHER, policy, SID, worker } from "./support/schedulerFixtures";

let urls: string[];
let pages: Array<() => Promise<Response>>;
let served: number;
beforeEach(() => {
  setCsrfToken("t"); urls = []; served = 0;
  vi.stubGlobal("fetch", (url: string) => {
    urls.push(url);
    if (url.includes("/scheduler?")) return pages[Math.min(served++, pages.length - 1)]();
    if (url.includes("/copy-policies/")) return json(200, policy("AUTHORIZED", SID, { reserved_candidates: 7 }));
    if (url.includes("/local-mandates/")) return json(200, mandate("ENABLED", SID, { reserved_local_calls: 9 }));
    return err(404, "NOT_FOUND", "no");
  });
});
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });

const none = { cancelled: false };

describe("findSeriesGrants", () => {
  it("walks with limit=100 and keeps only what belongs to the schedule", async () => {
    pages = [() => json(200, indexPage({ copy_policies: [policy("AUTHORIZED", SID), policy("PLANNED", OTHER, { policy_id: "x".repeat(64) })],
      local_mandates: [mandate("ENABLED", SID)] }))];
    const grants = await findSeriesGrants("news", SID, none);
    expect(urls).toEqual(["/control/v1/p/news/scheduler?limit=100"]);
    expect(grants.policies).toHaveLength(1);
    expect(grants.mandates).toHaveLength(1);
    expect(grants.revision).toBe("rev");
    expect(grants.complete).toBe(true);
  });
  it("is bounded to 10 pages", async () => {
    pages = [() => json(200, indexPage({}, "more"))];
    const grants = await findSeriesGrants("news", SID, none);
    expect(urls.filter((u) => u.includes("/scheduler?"))).toHaveLength(10);
    expect(grants.complete).toBe(false);
  });
  it("stops requesting when the page is cancelled", async () => {
    const token = { cancelled: false };
    pages = [() => { token.cancelled = true; return json(200, indexPage({}, "more")); }];
    await findSeriesGrants("news", SID, token).catch(() => undefined);
    expect(urls.filter((u) => u.includes("/scheduler?"))).toHaveLength(1);
  });
});

describe("refreshGrants", () => {
  it("re-reads only the matched ids and a one-row probe while the revision is unchanged", async () => {
    pages = [() => json(200, indexPage({ copy_policies: [policy("AUTHORIZED", SID)], local_mandates: [mandate("ENABLED", SID)] }))];
    const first = await findSeriesGrants("news", SID, none);
    urls.length = 0;
    pages = [() => json(200, indexPage({ workers: { supervisor: worker("supervisor", "ALIVE"), operations: worker("operations", "ALIVE"),
      mandates: { ["m".repeat(64)]: worker("m", "STALE") } } }))];
    served = 0;
    const next = await refreshGrants("news", SID, first, none);
    expect(urls.sort()).toEqual([
      `/control/v1/p/news/copy-policies/${"p".repeat(64)}`,
      `/control/v1/p/news/local-mandates/${"m".repeat(64)}`,
      "/control/v1/p/news/scheduler?limit=1",
    ].sort());
    expect(next.policies[0].reserved_candidates).toBe(7);
    expect(next.mandates[0].reserved_local_calls).toBe(9);
    expect(next.mandateWorkers["m".repeat(64)].worker.state).toBe("STALE");
  });
  it("keeps the last known worker, with its own time, when the probe row does not carry it", async () => {
    pages = [() => json(200, indexPage({ local_mandates: [mandate("ENABLED", SID)],
      workers: { supervisor: worker("supervisor", "ALIVE"), operations: worker("operations", "ALIVE"), mandates: { ["m".repeat(64)]: worker("m", "ALIVE") } } }))];
    const first = await findSeriesGrants("news", SID, none);
    served = 0;
    pages = [() => json(200, indexPage())];
    const next = await refreshGrants("news", SID, first, none);
    expect(next.mandateWorkers["m".repeat(64)].worker.state).toBe("ALIVE");
    expect(next.mandateWorkers["m".repeat(64)].at).toBe(first.mandateWorkers["m".repeat(64)].at);
  });
  it("walks again when the revision changed", async () => {
    pages = [() => json(200, indexPage({ copy_policies: [policy("AUTHORIZED", SID)] }))];
    const first = await findSeriesGrants("news", SID, none);
    urls.length = 0; served = 0;
    pages = [
      () => json(200, indexPage({ archive: { limit: 1, offset: 0, revision: "rev2", next_cursor: null, total: { schedules: 0, copy_policies: 0, local_mandates: 0 } } })),
      () => json(200, indexPage({ copy_policies: [policy("AUTHORIZED", SID), policy("PLANNED", SID, { policy_id: "z".repeat(64) })] })),
    ];
    const next = await refreshGrants("news", SID, first, none);
    expect(urls).toEqual(["/control/v1/p/news/scheduler?limit=1", "/control/v1/p/news/scheduler?limit=100"]);
    expect(next.policies).toHaveLength(2);
  });
});
