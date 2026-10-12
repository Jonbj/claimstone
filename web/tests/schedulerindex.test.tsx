// The project's Scheduler index: the processes strip, the series (newest first), paging, the
// signed-out line. A process that is not alive is an operational alert and never hides a series.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import SchedulerPage from "@/pages/SchedulerPage";
import {
  err, FUTURE, indexPage, json, mandate, OTHER, PAST, policy, schedule, SID, stub, worker,
} from "./support/schedulerFixtures";

function mount() {
  render(
    <MemoryRouter initialEntries={["/p/news/scheduler"]}>
      <LocaleProvider>
        <SessionProvider>
          <Routes><Route path="/p/:project/scheduler" element={<SchedulerPage />} /></Routes>
        </SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

const TWO = () => indexPage({
  schedules: [schedule("PLANNED", {}, PAST, SID), schedule("AUTHORIZED", {}, FUTURE, OTHER)],
  copy_policies: [policy("AUTHORIZED", OTHER)],
  local_mandates: [mandate("ENABLED", OTHER, { mandate_id: "m1".padEnd(64, "m") }), mandate("DISABLED", null, { mandate_id: "m2".padEnd(64, "m"), remaining_local_calls: 42 })],
});

describe("Scheduler index", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

  it("lists the series newest first, state words in titles, the UTC window, grants by schedule_id", async () => {
    stub({ index: [() => json(200, TWO())] });
    mount();
    const rows = await screen.findAllByRole("listitem", { name: /^Series / });
    expect(rows).toHaveLength(2);
    // newest first: the 2099 window precedes the 2025 one
    expect(rows[0].getAttribute("aria-label")).toContain(OTHER.slice(0, 12));
    expect(rows[1].getAttribute("aria-label")).toContain(SID.slice(0, 12));
    const first = within(rows[0]);
    expect(first.getAllByTitle("AUTHORIZED")[0].textContent).toBe("Authorized");
    expect(first.getByText("1 Jan 2099, 00:00 UTC → 28 Feb 2099, 00:00 UTC")).toBeTruthy();
    expect(first.getByText("2 rounds")).toBeTruthy();
    expect(first.getByText("up to 480 requests")).toBeTruthy();
    expect(first.getByText(/Copies/).parentElement!.textContent).toContain("Authorized");
    expect(first.getByText(/Local model/).parentElement!.textContent).toContain("Enabled");
    const second = within(rows[1]);
    expect(second.getByText(/Copies/).parentElement!.textContent).toContain("not decided");
    expect(second.getByText(/Local model/).parentElement!.textContent).toContain("not decided");
    expect(first.getByRole("link", { name: /Open series/ }).getAttribute("href"))
      .toBe(`/p/news/scheduler/s/${OTHER}`);
    // the unattached mandate is listed apart
    const apart = screen.getByRole("region", { name: "Local-model mandates on a single flow" });
    expect(within(apart).getByTitle("DISABLED")).toBeTruthy();
    expect(within(apart).getByText("42 calls left")).toBeTruthy();
    expect(screen.getByRole("link", { name: "New series" }).getAttribute("href"))
      .toBe("/p/news/scheduler/new");
  });

  it("shows an unknown state word verbatim", async () => {
    stub({ index: [() => json(200, indexPage({ schedules: [schedule("SOMETHING_NEW")] }))] });
    mount();
    const words = await screen.findAllByTitle("SOMETHING_NEW");
    for (const word of words) expect(word.textContent).toBe("SOMETHING_NEW");
  });

  it("an ALIVE supervisor shows no alert; a STALE one is an operational alert and the series stay listed", async () => {
    stub({ index: [() => json(200, TWO())] });
    mount();
    await screen.findAllByRole("listitem", { name: /^Series / });
    expect(screen.queryByRole("status", { name: /Automatic scanning/ })).toBeNull();
    expect(screen.getByText(/means the process is scanning, not that anything advanced/)).toBeTruthy();
    cleanup();
    stub({ index: [() => json(200, indexPage({
      schedules: [schedule("AUTHORIZED")],
      workers: { supervisor: worker("supervisor", "STALE", { last_seen_at: "2026-10-12T08:15:00+00:00", age_seconds: 9000 }),
                 operations: worker("operations", "ALIVE"), mandates: {} },
    }))] });
    mount();
    const alert = await screen.findByRole("status", { name: /Automatic scanning/ });
    expect(alert.textContent).toContain("The process that runs approved work is not responding. Approved work waits. This is a process signal, not a research result.");
    expect(alert.textContent).not.toContain("not running");
    expect(alert.textContent).toContain("12 Oct 2026, 08:15 UTC");
    expect(screen.getAllByRole("listitem", { name: /^Series / })).toHaveLength(1);
  });

  it.each(["STALE", "STOPPED", "UNKNOWN"])("the supervisor %s alerts; STOPPED and UNKNOWN too", async (state) => {
    stub({ index: [() => json(200, indexPage({ workers: { supervisor: worker("supervisor", state), operations: worker("operations", "ALIVE"), mandates: {} } }))] });
    mount();
    expect(await screen.findByRole("status", { name: /Automatic scanning/ })).toBeTruthy();
  });

  it.each(["NOT_STARTED", "STALE", "STOPPED"])("the operations worker %s is shown neutrally with the contract's sentence, not as an alert", async (state) => {
    stub({ index: [() => json(200, indexPage({ schedules: [schedule("AUTHORIZED")],
      workers: { supervisor: worker("supervisor", "ALIVE"), operations: worker("operations", state), mandates: {} } }))] });
    mount();
    await screen.findAllByRole("listitem", { name: /^Series / });
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText(/Normally stopped between supervisor passes/)).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Processes" })).getByTitle(state)).toBeTruthy();
  });

  it("a STALE supervisor leaves the series rows visible with their counts", async () => {
    stub({ index: [() => json(200, indexPage({ schedules: [schedule("AUTHORIZED")],
      workers: { supervisor: worker("supervisor", "STALE"), operations: worker("operations", "ALIVE"), mandates: {} } }))] });
    mount();
    const row = (await screen.findAllByRole("listitem", { name: /^Series / }))[0];
    expect(within(row).getByText("2 rounds")).toBeTruthy();
    expect(within(row).getByText("up to 480 requests")).toBeTruthy();
  });

  it("says '1 round' in the singular", async () => {
    stub({ index: [() => json(200, indexPage({ schedules: [schedule("PLANNED", { plan: { ...schedule("PLANNED").plan, entries: schedule("PLANNED").plan.entries.slice(0, 1) } })] }))] });
    mount();
    expect(await screen.findByText("1 round")).toBeTruthy();
  });

  it("loads more with the cursor and appends; a 409 restarts at page one with a notice", async () => {
    const urls = stub({ index: [
      () => json(200, indexPage({ schedules: [schedule("PLANNED", {}, PAST, SID)] }, "c1")),
      () => err(409, "ARCHIVE_CHANGED", "scheduler archive changed; restart paging"),
      () => json(200, indexPage({ schedules: [schedule("PLANNED", {}, PAST, OTHER)] })),
    ] });
    mount();
    await screen.findAllByRole("listitem", { name: /^Series / });
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("The list changed while you were reading it; starting again from the first page.");
    // the notice goes with the next successful read
    await waitFor(() => expect(screen.queryByRole("button", { name: "Load more" })).toBeNull());
    const scheduler = urls.filter((u) => u.includes("/scheduler"));
    expect(scheduler).toEqual([
      "/control/v1/p/news/scheduler?limit=25",
      "/control/v1/p/news/scheduler?limit=25&cursor=c1",
      "/control/v1/p/news/scheduler?limit=25",
    ]);
    await waitFor(() => {
      const rows = screen.getAllByRole("listitem", { name: /^Series / });
      expect(rows).toHaveLength(1);
      expect(rows[0].getAttribute("aria-label")).toContain(OTHER.slice(0, 12));
    });
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("appends the next page", async () => {
    const urls = stub({ index: [
      () => json(200, indexPage({ schedules: [schedule("PLANNED", {}, PAST, SID)] }, "c1")),
      () => json(200, indexPage({ schedules: [schedule("PLANNED", {}, FUTURE, OTHER)] })),
    ] });
    mount();
    await screen.findAllByRole("listitem", { name: /^Series / });
    // grants of a series cannot be called "not decided" while more pages remain
    expect(screen.getAllByText("not loaded yet").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getAllByRole("listitem", { name: /^Series / })).toHaveLength(2));
    expect(urls).toContain("/control/v1/p/news/scheduler?limit=25&cursor=c1");
  });

  it("empty: says so and offers the New series button", async () => {
    stub({});
    mount();
    expect(await screen.findByText("No series yet.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "New series" })).toBeTruthy();
  });

  it("signed out: no scheduler request and a sign-in link", async () => {
    const urls = stub({ signedIn: false });
    mount();
    const link = await screen.findByRole("link", { name: "Sign in" });
    expect(link.getAttribute("href")).toBe("/login?next=%2Fp%2Fnews%2Fscheduler");
    expect(urls.some((u) => u.includes("/scheduler"))).toBe(false);
  });

  it("renders in Italian: labels translated, the server's word in the title", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    stub({ index: [() => json(200, TWO())] });
    mount();
    await screen.findAllByRole("listitem", { name: /^Serie / });
    const word = screen.getAllByTitle("AUTHORIZED")[0];
    expect(word.textContent).toBe("Autorizzato");
    expect(screen.getByRole("link", { name: "Nuova serie" })).toBeTruthy();
    expect(screen.getAllByText("non deciso").length).toBeGreaterThan(0);
  });
});

describe("Scheduler index refresh", () => {
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
  const indexUrls = (urls: string[]) => urls.filter((u) => u.includes("/scheduler"));

  it("re-reads page one and every cursor already followed, in order, every 15 s", async () => {
    const urls = stub({ indexFor: (url) => json(200, url.includes("cursor=c1")
      ? indexPage({ schedules: [schedule("PLANNED", {}, FUTURE, OTHER)] })
      : indexPage({ schedules: [schedule("PLANNED", {}, PAST, SID)] }, "c1")) });
    mount();
    await screen.findAllByRole("listitem", { name: /^Series / });
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getAllByRole("listitem", { name: /^Series / })).toHaveLength(2));
    urls.length = 0;
    await tick(15_000);
    expect(indexUrls(urls)).toEqual([
      "/control/v1/p/news/scheduler?limit=25",
      "/control/v1/p/news/scheduler?limit=25&cursor=c1",
    ]);
  });

  it("does not start a read while the previous one is still pending", async () => {
    let calls = 0;
    const urls = stub({ index: [() => { calls += 1; return calls === 1 ? json(200, indexPage({ schedules: [schedule("PLANNED")] })) : new Promise<Response>(() => undefined); }] });
    mount();
    await screen.findAllByRole("listitem", { name: /^Series / });
    urls.length = 0;
    await tick(15_000);
    await tick(15_000);
    await tick(15_000);
    expect(indexUrls(urls)).toHaveLength(1);
  });

  it("pauses while the tab is hidden", async () => {
    const urls = stub({ index: [() => json(200, indexPage({ schedules: [schedule("PLANNED")] }))] });
    mount();
    await screen.findAllByRole("listitem", { name: /^Series / });
    urls.length = 0;
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await tick(60_000);
    expect(indexUrls(urls)).toHaveLength(0);
  });
});
