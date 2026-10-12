// A flow that belongs to a series says so and links to it. The relation comes from the schedule's
// entries in the scheduler index, which needs a session: signed out there is no request and no chip.
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import ProjectPage from "@/pages/ProjectPage";
import { err, indexPage, json, schedule, SID, stub } from "./support/schedulerFixtures";

const FLOWS = [
  { flow_id: "flow1", selector: { round: "update-2026-11", manifest_only: false }, title: "November update" },
  { flow_id: "lone", selector: { round: null, manifest_only: false }, title: "Whole store" },
];

function mount() {
  render(
    <MemoryRouter initialEntries={["/p/news?details=1"]}>
      <LocaleProvider>
        <SessionProvider>
          <Routes><Route path="/p/:project" element={<ProjectPage />} /></Routes>
        </SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

describe("the series chip on a flow card", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

  it("names the series and the round of a flow that is in one, and only that flow", async () => {
    stub({ flows: FLOWS, index: [() => json(200, indexPage({ schedules: [schedule("AUTHORIZED")] }))] });
    mount();
    const chip = await screen.findByRole("link", { name: "Series · round update-2026-11" });
    expect(chip.getAttribute("href")).toBe(`/p/news/scheduler/s/${SID}`);
    expect(screen.getAllByRole("link", { name: /^Series/ })).toHaveLength(1);
    const card = screen.getByRole("link", { name: /Whole store/ }).closest("li")!;
    expect(within(card).queryByRole("link", { name: /^Series/ })).toBeNull();
  });

  it("signed out: no scheduler request and no chip", async () => {
    const urls = stub({ signedIn: false, flows: FLOWS });
    mount();
    await screen.findByRole("link", { name: /November update/ });
    expect(urls.some((u) => u.includes("/scheduler"))).toBe(false);
    expect(screen.queryByRole("link", { name: /^Series/ })).toBeNull();
  });

  it("a failing index read leaves the cards as they are", async () => {
    stub({ flows: FLOWS, index: [() => err(500, "INTERNAL", "boom")] });
    mount();
    await screen.findByRole("link", { name: /November update/ });
    expect(screen.queryByRole("link", { name: /^Series/ })).toBeNull();
  });

  it("reads the index once, with the default page size", async () => {
    const urls = stub({ flows: FLOWS, index: [() => json(200, indexPage({ schedules: [schedule("AUTHORIZED")] }))] });
    mount();
    await screen.findByRole("link", { name: "Series · round update-2026-11" });
    expect(urls.filter((u) => u.includes("/control/v1/p/news/scheduler"))).toEqual(["/control/v1/p/news/scheduler?limit=25"]);
  });

  it("in Italian", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    stub({ flows: FLOWS, index: [() => json(200, indexPage({ schedules: [schedule("AUTHORIZED")] }))] });
    mount();
    expect(await screen.findByRole("link", { name: "Serie · round update-2026-11" })).toBeTruthy();
  });
});
