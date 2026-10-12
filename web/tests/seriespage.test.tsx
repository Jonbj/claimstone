// The series page (read-only): the plan, the calendar, the copy policy, the local mandate and the
// result, with the rounds on top. The dossier is read once on load and again only when the poll
// fires; if it fails, the other steps still render.
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import SeriesPage from "@/pages/SeriesPage";
import {
  admission, authorized, err, indexPage, json, mandate, policy, SID, schedule, stub, worker,
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
    expect(screen.queryByRole("button", { name: /authori[sz]e|create/i })).toBeNull();
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
    expect(within(result).getByText("the schedule is not authorized")).toBeTruthy();
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
    // The policy says in so many words that it buys nothing; that denial is the one allowed mention.
    expect(step.textContent).toContain("admits no source scientifically, buys nothing and signs nothing");
    expect(document.body.textContent!.replace("buys nothing", "")).not.toMatch(/buy|purchase|pay|acquista|compra|paga/i);
  });

  it("no purchase wording in Italian either", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    stub({ schedule: () => json(200, schedule("AUTHORIZED")), index: [withGrants()] });
    mount();
    await screen.findByText(/qwen-extract/);
    const step = screen.getByRole("region", { name: /Copie future/ });
    expect(step.textContent).toContain("non ammette nessuna fonte dal punto di vista scientifico, non compra nulla e non firma nulla");
    expect(document.body.textContent!.replace("non compra nulla", "")).not.toMatch(/buy|purchase|pay|acquista|compra|paga/i);
  });

  it("a STALE mandate worker shows an operational process line; the mandate state stays visible", async () => {
    stub({
      schedule: () => json(200, schedule("AUTHORIZED")),
      index: [() => json(200, indexPage({
        schedules: [schedule("AUTHORIZED")], local_mandates: [mandate("ENABLED", SID, { pending_batches: [{ batch_id: "b1", stage: "extract", awaiting_approval: 2, max_total_requests: 7 }] })],
        workers: { supervisor: worker("supervisor", "ALIVE"), operations: worker("operations", "ALIVE"),
                   mandates: { ["m".repeat(64)]: worker("m", "STALE") } },
      }))],
    });
    mount();
    const step = await screen.findByRole("region", { name: /Local model/ });
    const process = await within(step).findByRole("status");
    expect(process.textContent).toContain("Process");
    expect(process.textContent).toContain("is not running");
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
    const urls = stub({ schedule: () => json(200, schedule("AUTHORIZED")) });
    mount();
    await screen.findByRole("region", { name: "Rounds" });
    const dossiers = () => urls.filter((u) => u.includes("periodic-dossiers")).length;
    expect(dossiers()).toBe(1);
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(dossiers()).toBe(1);
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
    expect(admission().found).toBe(8); // fixture sanity
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
