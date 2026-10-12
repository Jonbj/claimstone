// The Scheduler tab: two links under a project's breadcrumb, on the project page, on the flow
// journey and on the scheduler pages; the Flows link never bounces a single-flow project back.
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProjectTabs from "@/components/ProjectTabs";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import CumulativeResultPage from "@/pages/CumulativeResultPage";
import NewSeriesPage from "@/pages/NewSeriesPage";
import SchedulerPage from "@/pages/SchedulerPage";
import SeriesPage from "@/pages/SeriesPage";

function mount(path: string) {
  render(
    <LocaleProvider>
      <SessionProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/p/:project" element={<ProjectTabs project="news" />} />
          <Route path="/p/:project/f/:sel" element={<ProjectTabs project="news" />} />
          <Route path="/p/:project/scheduler" element={<SchedulerPage />} />
          <Route path="/p/:project/scheduler/new" element={<NewSeriesPage />} />
          <Route path="/p/:project/scheduler/s/:schedule" element={<SeriesPage />} />
          <Route path="/p/:project/scheduler/s/:schedule/result" element={<CumulativeResultPage />} />
        </Routes>
      </MemoryRouter>
      </SessionProvider>
    </LocaleProvider>,
  );
}

describe("ProjectTabs", () => {
  // The scheduler pages need a session; nobody is signed in here, and the tabs do not care.
  beforeEach(() => {
    vi.stubGlobal("fetch", () => Promise.resolve(new Response(
      JSON.stringify({ error: { code: "UNAUTHORIZED", message: "not signed in" } }),
      { status: 401, headers: { "Content-Type": "application/json" } })));
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

  it("on the project page: Flows is current and keeps the details view; Scheduler points to the index", () => {
    mount("/p/news");
    const flows = screen.getByRole("link", { name: "Flows" });
    expect(flows.getAttribute("href")).toBe("/p/news?details=1");
    expect(flows.getAttribute("aria-current")).toBe("page");
    const scheduler = screen.getByRole("link", { name: "Scheduler" });
    expect(scheduler.getAttribute("href")).toBe("/p/news/scheduler");
    expect(scheduler.getAttribute("aria-current")).toBeNull();
  });

  it("on the flow journey: the same two links, Flows current", () => {
    mount("/p/news/f/abc");
    expect(screen.getByRole("link", { name: "Flows" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Scheduler" }).getAttribute("href")).toBe("/p/news/scheduler");
  });

  it.each([
    ["/p/news/scheduler", "Scheduler"],
    ["/p/news/scheduler/new", "New series"],
    ["/p/news/scheduler/s/abc", "Series abc"],
    ["/p/news/scheduler/s/abc/result", "Cumulative result"],
  ])("%s renders its title with Scheduler current", (path, title) => {
    mount(path);
    expect(screen.getByRole("heading", { name: title })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Scheduler" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Flows" }).getAttribute("aria-current")).toBeNull();
  });

  it("percent-encodes the project name", () => {
    render(
      <LocaleProvider>
        <MemoryRouter initialEntries={["/p/a%20b"]}>
          <ProjectTabs project="a b" />
        </MemoryRouter>
      </LocaleProvider>,
    );
    expect(screen.getByRole("link", { name: "Scheduler" }).getAttribute("href")).toBe("/p/a%20b/scheduler");
  });

  it("is in Italian when the locale is Italian", () => {
    localStorage.setItem(STORAGE_KEY, "it");
    mount("/p/news");
    expect(screen.getByRole("navigation", { name: "Sezioni del progetto" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Flussi" })).toBeTruthy();
  });
});
