// The series page (read-only): the plan, the calendar, the copy policy, the local mandate and the
// result, with the rounds on top. The dossier is read once on load and again only when the poll
// fires; if it fails, the other steps still render.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { expectNoPurchaseWording } from "./support/purchase";
import { SessionProvider } from "@/lib/session";
import SeriesPage from "@/pages/SeriesPage";
import {
  admission, authorized, dossier, err, indexPage, json, mandate, policy, SID, schedule, stub, worker,
} from "./support/schedulerFixtures";

// The poll is the page's only trigger for reading again: capture its callback and fire it by hand.
let firePoll: () => void = () => undefined;
vi.mock("@/hooks/usePoll", () => ({
  usePoll: (_project: string | null, onChange: () => void) => { firePoll = onChange; },
}));

function mount() {
  render(
    <MemoryRouter initialEntries={[`/p/news/scheduler/s/${SID}`]}>
      <LocaleProvider>
        <SessionProvider>
          <Routes><Route path="/p/:project/scheduler/s/:schedule" element={<SeriesPage />} /></Routes>
        </SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

const withGrants = (over = {}) => () => json(200, indexPage({
  schedules: [schedule("AUTHORIZED")], copy_policies: [policy("AUTHORIZED")],
  local_mandates: [mandate("ENABLED")], ...over,
}));

describe("Series page", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear(); });

  it("PLANNED: every round says planned, the calendar permits nothing, windows carry UTC", async () => {
    stub({ schedule: () => json(200, schedule("PLANNED", {}, [["2099-01-01T00:00:00+00:00", "2099-01-31T00:00:00+00:00"], ["2099-02-01T00:00:00+00:00", "2099-02-28T00:00:00+00:00"]])) });
    mount();
    const timeline = await screen.findByRole("region", { name: "Rounds" });
    expect(within(timeline).getAllByText("planned")).toHaveLength(2);
    expect(within(timeline).getByText("1 Jan 2099, 00:00 UTC → 31 Jan 2099, 00:00 UTC")).toBeTruthy();
    expect(screen.getByText("No request is permitted yet.")).toBeTruthy();
    // Authorize exists but permits nothing by itself: it waits for the box to be ticked.
    expect(screen.getByRole("button", { name: "Authorize the calendar" }).hasAttribute("disabled")).toBe(true);
  });

  it("AUTHORIZED: shows who authorized and when, from the events", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED", { events: [authorized("Bea Operator")] })) });
    mount();
    const calendar = await screen.findByRole("region", { name: /Calendar/ });
    expect(within(calendar).getByText(/Bea Operator/)).toBeTruthy();
    expect(within(calendar).getByText(/1 Oct 2026, 09:30 UTC/)).toBeTruthy();
    expect(within(calendar).queryByText("No request is permitted yet.")).toBeNull();
  });

  it("a round with 2 of 3 searches shows 2 / 3, and the dossier state is the server's word, not 'ready'", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED")) });
    mount();
    const timeline = await screen.findByRole("region", { name: "Rounds" });
    expect(within(timeline).getByText("2 / 3")).toBeTruthy();
    expect(within(timeline).getByText("COMPLETED: 3")).toBeTruthy();
    const result = screen.getByRole("region", { name: /Result/ });
    expect(within(result).getByText("WAITING_FOR_SCHEDULE")).toBeTruthy();
    expect(within(result).getByText("SCHEDULE_OR_ROUND_INCOMPLETE")).toBeTruthy();
    expect(screen.queryByText(/READY/)).toBeNull();
    expect(within(result).getByRole("link", { name: "Open the cumulative result" }).getAttribute("href"))
      .toBe(`/p/news/scheduler/s/${SID}/result`);
  });

  it("keeps found in the denominator: 3 confirmed of 8 found; a round with none found is not a failure", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED")) });
    mount();
    const timeline = await screen.findByRole("region", { name: "Rounds" });
    expect(within(timeline).getByText("3 / 8")).toBeTruthy();
    expect(within(timeline).getAllByText("INSUFFICIENT_ACQUISITION")).toHaveLength(2);
    expect(within(timeline).getByText("no candidates found yet")).toBeTruthy();
  });

  it("a copy policy attached by schedule_id shows hosts, classes, both caps and the product, and nothing about buying", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED")), index: [withGrants()] });
    mount();
    const step = await screen.findByRole("region", { name: /Future copies/ });
    await within(step).findByText(/europepmc\.org/);
    expect(within(step).getByText(/arxiv\.org/)).toBeTruthy();
    expect(within(step).getByText(/PREPRINT/)).toBeTruthy();
    expect(within(step).getByText("10 × 3 = 30")).toBeTruthy();
    expect(within(step).getByText(/2 \/ 10/)).toBeTruthy();
    expect(within(step).getByText(/robots/i)).toBeTruthy();
    await screen.findByText(/qwen-extract/);
    // The policy and the mandate say in so many words that they buy nothing; those two sentences are
    // asserted present and taken out, and nothing else on the page may speak of buying.
    expect(step.textContent).toContain("admits no source scientifically, buys nothing and signs nothing");
    expectNoPurchaseWording(document.body.textContent!, "en", ["sched.policy.forbids", "sched.mandate.forbids"]);
  });

  it("no purchase wording in Italian either", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    stub({ schedule: () => json(200, schedule("AUTHORIZED")), index: [withGrants()] });
    mount();
    await screen.findByText(/qwen-extract/);
    const step = screen.getByRole("region", { name: /Copie future/ });
    expect(step.textContent).toContain("non ammette nessuna fonte dal punto di vista scientifico, non compra nulla e non firma nulla");
    expectNoPurchaseWording(document.body.textContent!, "it", ["sched.policy.forbids", "sched.mandate.forbids"]);
  });

  it.each(["STALE", "STOPPED", "NOT_STARTED"])("a %s mandate worker is a neutral process line, never an alert; the mandate state stays visible", async (state) => {
    stub({
      schedule: () => json(200, schedule("AUTHORIZED")),
      index: [() => json(200, indexPage({
        schedules: [schedule("AUTHORIZED")], local_mandates: [mandate("ENABLED", SID, { pending_batches: [{ batch_id: "b1", stage: "extract", awaiting_approval: 2, max_total_requests: 7 }] })],
        workers: { supervisor: worker("supervisor", "ALIVE"), operations: worker("operations", "ALIVE"),
                   mandates: { ["m".repeat(64)]: worker("m", state) } },
      }))],
    });
    mount();
    const step = await screen.findByRole("region", { name: /Local model/ });
    await within(step).findByText(/Normally stopped between supervisor passes/);
    // an always-present live region of the grant panel is empty; no process alert is ever spoken here
    expect(within(step).queryAllByRole("status").filter((e) => e.textContent)).toHaveLength(0);
    expect(within(step).getByText("Process")).toBeTruthy();
    expect(within(step).getByTitle(state)).toBeTruthy();
    expect(within(step).getAllByTitle("ENABLED").length).toBeGreaterThan(0);
    expect(within(step).getByText(/5 \/ 100/)).toBeTruthy();
    expect(within(step).getByText(/2 awaiting approval/)).toBeTruthy();
  });

  it("a mandate's disabled_by is rendered by name", async () => {
    stub({
      schedule: () => json(200, schedule("AUTHORIZED")),
      index: [() => json(200, indexPage({ schedules: [schedule("AUTHORIZED")],
        local_mandates: [mandate("DISABLED", SID, { disabled_by: { operator: "cy", name: "Cy Off" } })] }))],
    });
    mount();
    expect(await screen.findByText(/Cy Off/)).toBeTruthy();
  });

  it("404 on the schedule says series not found", async () => {
    stub({ schedule: () => err(404, "NOT_FOUND", "no such schedule") });
    mount();
    expect(await screen.findByText("Series not found.")).toBeTruthy();
  });

  it("a failing dossier replaces only the timeline with a named banner; the other steps render", async () => {
    stub({
      schedule: () => json(200, schedule("AUTHORIZED", { events: [authorized()] })),
      dossier: () => err(409, "REGISTRY_DRIFT", "the registry changed under its version"),
      index: [withGrants()],
    });
    mount();
    const banner = await screen.findByRole("alert");
    expect(banner.textContent).toContain("REGISTRY_DRIFT");
    expect(banner.textContent).toContain("the registry changed under its version");
    expect(screen.queryByRole("region", { name: "Rounds" })).toBeNull();
    expect(screen.getByRole("region", { name: /Plan/ })).toBeTruthy();
    expect(screen.getByRole("region", { name: /Calendar/ })).toBeTruthy();
    await screen.findByText(/europepmc\.org/);
  });

  it("reads the dossier once on load and again only when the poll fires", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const urls = stub({ schedule: () => json(200, schedule("AUTHORIZED")) });
    mount();
    await screen.findByRole("region", { name: "Rounds" });
    const dossiers = () => urls.filter((u) => u.includes("periodic-dossiers")).length;
    expect(dossiers()).toBe(1);
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(dossiers()).toBe(1);
    // the dossier is read at most once every 45 s: a poll at once changes nothing, one after it does
    await act(async () => { firePoll(); });
    expect(dossiers()).toBe(1);
    vi.setSystemTime(Date.now() + 46_000);
    await act(async () => { firePoll(); });
    await waitFor(() => expect(dossiers()).toBe(2));
  });

  it("walks at most 10 index pages when every answer has a next cursor, then says grants are not loaded", async () => {
    const urls = stub({
      schedule: () => json(200, schedule("AUTHORIZED")),
      index: [() => json(200, indexPage({ schedules: [] }, "more"))],
    });
    mount();
    await screen.findByText(/Grants not loaded/);
    await waitFor(() => expect(urls.filter((u) => u.includes("/scheduler?")).length).toBe(10));
  });

  it("renders in Italian", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    stub({ schedule: () => json(200, schedule("AUTHORIZED", { events: [authorized()] })), index: [withGrants()] });
    mount();
    const calendar = await screen.findByRole("region", { name: /Calendario/ });
    expect(within(calendar).getByTitle("AUTHORIZED").textContent).toBe("Autorizzato");
    expect(screen.getByRole("region", { name: /Copie future/ })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Round" })).toBeTruthy();
    expect(screen.getAllByText("Cosa permette").length).toBeGreaterThan(0);
  });
});

describe("Series page fidelity", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear(); });

  const round = (over: Record<string, unknown> = {}, adm: Record<string, unknown> = {}, i = 1) => ({
    round: `Round ${i}`, flow_id: `flow${i}`, binding_state: "CURRENT", not_before: "2025-01-01T00:00:00+00:00",
    expires_at: "2025-01-31T00:00:00+00:00", operations: { COMPLETED: 3 }, successful_queries: 3, planned_queries: 3,
    admission: admission(adm), ...over,
  });

  it("an event actor from the CLI (uid and login) is shown by login; an empty identity is a dash, not nothing", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED", { events: [
      { event: "authorized", at: "2026-10-01T09:30:00+00:00", identity: { uid: 1000, login: "stefano" } },
      { event: "revoked", at: "2026-10-02T09:30:00+00:00", identity: { uid: 1001 } },
      { event: "authorized", at: "2026-10-03T09:30:00+00:00", identity: {} },
    ] })) });
    mount();
    const calendar = await screen.findByRole("region", { name: /Calendar/ });
    expect(within(calendar).getByText(/stefano/)).toBeTruthy();
    expect(within(calendar).getByText(/uid 1001/)).toBeTruthy();
    expect(within(calendar).getByText(/3 Oct 2026, 09:30 UTC/).textContent).toContain("—");
  });

  it("a mandate disabled from the CLI shows who; the enabling actor and time come from the mandate itself", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED")), index: [() => json(200, indexPage({
      schedules: [schedule("AUTHORIZED")],
      local_mandates: [mandate("DISABLED", SID, {
        disabled_by: { uid: 1000, login: "stefano" },
        mandate: { schedule_id: SID, extract_model: "a", review_model: "b", max_total_local_calls: 100,
                   authorized_by: { uid: 1001, login: "ada" }, created_ns: Date.parse("2026-10-01T09:30:00Z") * 1e6 } as never,
      })] }))] });
    mount();
    const step = await screen.findByRole("region", { name: /Local model/ });
    expect(await within(step).findByText("Disabled by stefano")).toBeTruthy();
    expect(within(step).getByText("Enabled by ada, 1 Oct 2026, 09:30 UTC")).toBeTruthy();
  });

  it("shows the rate with its basis, the upper bound, final and every blocking entry beside the status", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED")), dossier: () => json(200, dossier({}, [
      round({}, { basis: "obtained", rate: 0.5, rate_upper: 0.5, status: "OK", final: false, blocking: ["awaiting_discovery", "awaiting_acquire"] }),
      round({}, { status: "OK", final: true, blocking: [] }, 2),
    ])) });
    mount();
    const timeline = await screen.findByRole("region", { name: "Rounds" });
    const cells = within(timeline).getAllByRole("listitem");
    expect(within(cells[0]).getByText(/rate 50\.0% \(basis: obtained\)/)).toBeTruthy();
    expect(within(cells[0]).getByText("not final")).toBeTruthy();
    expect(within(cells[0]).getByText("Blocking: awaiting_discovery, awaiting_acquire")).toBeTruthy();
    expect(within(cells[0]).getByText("OK")).toBeTruthy();
    expect(within(cells[1]).getByText(/rate 37\.5% \(basis: confirmed\)/)).toBeTruthy();
    expect(within(cells[1]).getByText("final")).toBeTruthy();
    expect(within(cells[1]).queryByText(/Blocking:/)).toBeNull();
    expect(within(cells[1]).getByText(/upper bound 50\.0%/)).toBeTruthy();
  });

  it("shows each round's binding state word and the earlier rounds of the lineage", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED")), dossier: () => json(200, {
      ...dossier({}, [round({ binding_state: "PROTOCOL_DRIFTED" })]),
      audit: { ...dossier().audit, rounds: [round({ binding_state: "PROTOCOL_DRIFTED" })],
        ancestor_rounds: [{ flow_id: "flowancestor1", round: "Round zero", binding_state: "CURRENT",
          admission: admission({ status: "OK", rate: 0.9, final: true, blocking: [] }) }] } }) });
    mount();
    const timeline = await screen.findByRole("region", { name: "Rounds" });
    expect(within(timeline).getByTitle("PROTOCOL_DRIFTED")).toBeTruthy();
    const earlier = within(timeline).getByRole("region", { name: "Earlier rounds" });
    expect(within(earlier).getByText("Round zero")).toBeTruthy();
    expect(within(earlier).getByText("flowancestor")).toBeTruthy();
    expect(within(earlier).getByTitle("CURRENT")).toBeTruthy();
    expect(within(earlier).getByText(/90\.0%/)).toBeTruthy();
    expect(within(earlier).getByText("OK")).toBeTruthy();
  });

  it("'planned' is for PLANNED, or AUTHORIZED with a window not yet open; a REVOKED schedule shows its state word", async () => {
    const future: [string, string][] = [["2099-01-01T00:00:00+00:00", "2099-01-31T00:00:00+00:00"]];
    stub({ schedule: () => json(200, schedule("AUTHORIZED", {}, future)), dossier: () => json(200, dossier({}, [round({ not_before: future[0][0] })])) });
    mount();
    expect(within(await screen.findByRole("region", { name: "Rounds" })).getByText("planned")).toBeTruthy();
    cleanup();
    stub({ schedule: () => json(200, schedule("REVOKED", {}, future)), dossier: () => json(200, dossier({}, [round({ not_before: future[0][0] })])) });
    mount();
    const timeline = await screen.findByRole("region", { name: "Rounds" });
    expect(within(timeline).queryByText("planned")).toBeNull();
    expect(within(timeline).getByTitle("REVOKED").textContent).toBe("Revoked");
  });

  it("two copy policies each carry their own state word; the heading chip and the first row's spend line are dropped", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED")), index: [() => json(200, indexPage({
      schedules: [schedule("AUTHORIZED")],
      copy_policies: [policy("AUTHORIZED", SID), policy("REVOKED", SID, { policy_id: "q".repeat(64) })] }))] });
    mount();
    const step = await screen.findByRole("region", { name: /Future copies/ });
    await within(step).findAllByText(/europepmc\.org/);
    expect(within(step).getByTitle("AUTHORIZED")).toBeTruthy();
    expect(within(step).getByTitle("REVOKED")).toBeTruthy();
    expect(within(step).getAllByRole("heading")[0].querySelector("[title]")).toBeNull();
    expect(within(step).queryByText("Up to 10 × 3 = 30 requests.")).toBeNull();
    expect(within(step).getAllByText("10 × 3 = 30")).toHaveLength(2);
  });

  it("one copy policy keeps the heading chip and its spend line, and still has a state word in its row", async () => {
    stub({ schedule: () => json(200, schedule("AUTHORIZED")), index: [withGrants()] });
    mount();
    const step = await screen.findByRole("region", { name: /Future copies/ });
    await within(step).findByText(/europepmc\.org/);
    expect(within(step).getAllByTitle("AUTHORIZED")).toHaveLength(2);
    expect(within(step).getByText("Up to 10 × 3 = 30 requests.")).toBeTruthy();
  });
});

describe("Series page texts", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });
  const mounted = () => stub({ schedule: () => json(200, schedule("AUTHORIZED")), index: [withGrants()] });

  it("the Calendar permits only the frozen discovery searches and says what it does not do", async () => {
    mounted(); mount();
    const calendar = await screen.findByRole("region", { name: /Calendar/ });
    expect(calendar.textContent).toContain("Only these frozen discovery searches, in these windows, up to this ceiling.");
    expect(calendar.textContent).toContain("It does not fetch copies, run the local model or give a verdict.");
  });

  it("the Local model step lists what it may do and what it cannot approve", async () => {
    mounted(); mount();
    const step = await screen.findByRole("region", { name: /Local model/ });
    const text = step.textContent!;
    expect(text).toContain("read and review the documents of this series' flows within the call cap");
    expect(text).toContain("run the network work that the Calendar and Future copies already authorize");
    expect(text).toContain("plan the copies the copy policy allows");
    expect(text).toContain("save the cumulative dossier when its gates pass");
    expect(text).toContain("approves no new network request, no paid model call and no purchase");
    expect(text).toContain("gives no verdict");
  });

  it("the policy names the fetch rules it leaves in force", async () => {
    mounted(); mount();
    const step = await screen.findByRole("region", { name: /Future copies/ });
    expect(step.textContent).toContain("robots.txt, the redirect checks, the refusal of non-global addresses and the per-domain failure budgets still apply");
  });

  it("the same in Italian", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    mounted(); mount();
    const step = await screen.findByRole("region", { name: /Copie future/ });
    expect(step.textContent).toContain("Restano in vigore robots.txt, i controlli sui reindirizzamenti");
    expect((await screen.findByRole("region", { name: /Calendario/ })).textContent).toContain("Non prende copie, non usa il modello locale e non dà un verdetto.");
    expect((await screen.findByRole("region", { name: /Modello locale/ })).textContent).toContain("Non approva nessuna nuova richiesta di rete");
  });

  it("the breadcrumb link is a touch target and the tables scroll sideways rather than the page", async () => {
    mounted(); mount();
    const plan = await screen.findByRole("region", { name: /Plan/ });
    expect(plan.querySelector("table")!.parentElement!.className).toContain("overflow-x-auto");
    expect(screen.getByRole("link", { name: "All series" }).className).toContain("min-h-11");
  });

  it("the copy button announces 'Copied' in an always-present live region and resets after 2 s", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    mounted(); mount();
    const plan = await screen.findByRole("region", { name: /Plan/ });
    const live = within(plan).getByRole("status");
    expect(live.textContent).toBe("");
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    fireEvent.click(within(plan).getByRole("button", { name: /Copy/ }));
    await act(async () => { await Promise.resolve(); });
    expect(live.textContent).toBe("Copied");
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(live.textContent).toBe("");
    vi.useRealTimers();
  });
});

describe("Series page refresh", () => {
  beforeEach(() => {
    setCsrfToken(null);
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });
  afterEach(() => {
    cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear();
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });
  const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
  const count = (urls: string[], part: string) => urls.filter((u) => u.includes(part)).length;
  const grantsStub = (extra = {}) => stub({
    schedule: () => json(200, schedule("AUTHORIZED")),
    index: [withGrants()],
    policyRead: () => json(200, policy("AUTHORIZED")),
    mandateRead: () => json(200, mandate("ENABLED")),
    ...extra,
  });

  it("every 15 s re-reads the schedule, a one-row probe and only the matched grants; the dossier waits 45 s", async () => {
    const urls = grantsStub();
    mount();
    await screen.findByText(/qwen-extract/);
    expect(urls.filter((u) => u.includes("/scheduler?"))).toEqual(["/control/v1/p/news/scheduler?limit=100"]);
    urls.length = 0;
    await tick(15_000);
    expect(count(urls, "/schedules/")).toBe(1);
    expect(urls.filter((u) => u.includes("/scheduler?"))).toEqual(["/control/v1/p/news/scheduler?limit=1"]);
    expect(count(urls, "/copy-policies/")).toBe(1);
    expect(count(urls, "/local-mandates/")).toBe(1);
    expect(count(urls, "periodic-dossiers")).toBe(0);
    await tick(15_000);
    expect(count(urls, "periodic-dossiers")).toBe(0);
    await tick(15_000);
    expect(count(urls, "periodic-dossiers")).toBe(1);
    expect(screen.getByText(/^As of /)).toBeTruthy();
  });

  it("never starts a second dossier read while one is in flight", async () => {
    let reads = 0;
    const urls = grantsStub({ dossier: () => { reads += 1; return reads === 1 ? json(200, dossier()) : new Promise<Response>(() => undefined); } });
    mount();
    await screen.findByText(/qwen-extract/);
    await screen.findByRole("region", { name: "Rounds" });
    await tick(45_000);
    await tick(45_000);
    await tick(45_000);
    expect(count(urls, "periodic-dossiers")).toBe(2);
  });

  it("pauses while the tab is hidden", async () => {
    const urls = grantsStub();
    mount();
    await screen.findByText(/qwen-extract/);
    urls.length = 0;
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await tick(120_000);
    expect(urls).toHaveLength(0);
  });

  it("a STALE supervisor elsewhere does not hide the calendar events or the round counts", async () => {
    grantsStub({ schedule: () => json(200, schedule("AUTHORIZED", { events: [authorized("Bea Operator")] })) });
    mount();
    expect(await screen.findByText(/Bea Operator/)).toBeTruthy();
    expect(screen.getByText("2 / 3")).toBeTruthy();
  });

  it("recomputes 'planned' as the window opens, without a reload", async () => {
    vi.setSystemTime(new Date("2026-10-12T10:00:00Z"));
    const opens: [string, string] = ["2026-10-12T10:00:20+00:00", "2026-10-30T00:00:00+00:00"];
    grantsStub({ schedule: () => json(200, schedule("AUTHORIZED", {}, [opens])),
      dossier: () => json(200, dossier({}, [{ round: "Round one", flow_id: "flow1", binding_state: "CURRENT", not_before: opens[0], expires_at: opens[1], operations: {}, successful_queries: 0, planned_queries: 3, admission: { found: 0, confirmed: 0, obtained: 0, rate: null, status: "INSUFFICIENT_ACQUISITION", basis: "obtained", rate_upper: null, final: false, blocking: [] } }])) });
    mount();
    const timeline = await screen.findByRole("region", { name: "Rounds" });
    expect(within(timeline).getByText("planned")).toBeTruthy();
    await tick(30_000);
    expect(within(screen.getByRole("region", { name: "Rounds" })).queryByText("planned")).toBeNull();
  });

  it("stops reading when the page is left", async () => {
    const urls = grantsStub();
    mount();
    await screen.findByText(/qwen-extract/);
    cleanup();
    urls.length = 0;
    await tick(120_000);
    expect(urls).toHaveLength(0);
  });
});
