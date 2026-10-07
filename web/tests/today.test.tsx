// F2: Today. Renders the API's fields, names a failed project without blanking the others,
// guards the Mark as seen button against double submission, and explains itself signed out.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider } from "@/lib/session";
import TodayPage from "@/pages/TodayPage";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

const TODAY = {
  operator: "o1",
  projects: [
    {
      project: "alpha", since: null, first_visit: true,
      changed: { counts: { extract: 3 }, undated_rows: 0, newest: [] },
      needs_you: {
        required: [
          { flow_id: "f1", type: "identity", subject: "cand-1", cause: "which paper?" },
          { flow_id: "f1", type: "adjudication", subject: "Q01", cause: "ready" },
        ],
        optional: [],
      },
      continues_without_you: [],
    },
    { project: "beta", error: "LedgerCorrupt: bad line 4" },
  ],
};

function mount(signedIn: boolean, onSeen?: () => Promise<Response>, today: unknown = TODAY,
               todayStatus = 200) {
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (url.startsWith("/control/v1/session") && !url.includes("end")) {
      return signedIn
        ? json(200, { operator: { id: "o1", name: "Ada" }, csrf_token: "t" })
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } });
    }
    if (url.startsWith("/control/v1/today")) return json(todayStatus, today);
    if (url.startsWith("/control/v1/seen") && init?.method === "POST") {
      return onSeen ? onSeen() : json(201, { seen: {} });
    }
    return json(404, { error: { code: "NOT_FOUND", message: "x" } });
  });
  render(
    <MemoryRouter initialEntries={["/"]}>
      <SessionProvider>
        <Routes><Route path="/" element={<TodayPage />} /></Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("F2: Today", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows first visit, counts, links, and a failed project beside a good one", async () => {
    mount(true);
    expect(await screen.findByText("first visit")).toBeTruthy();
    expect(screen.getByText("extract")).toBeTruthy();
    expect(screen.getByRole("link", { name: "cand-1" }).getAttribute("href"))
      .toBe("/p/alpha/f/f1/decisions");
    expect(screen.getByRole("link", { name: "Q01" }).getAttribute("href"))
      .toBe("/p/alpha/f/f1/q/Q01");
    expect(screen.getByTestId("project-error").textContent).toContain("bad line 4");
  });

  it("disables Mark as seen while its request runs", async () => {
    let finish!: (r: Response) => void;
    const pending = new Promise<Response>((r) => (finish = r));
    mount(true, () => pending);
    const button = (await screen.findAllByRole("button", { name: "Mark as seen" }))[0];
    fireEvent.click(button);
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(true));
    fireEvent.click(button);
    finish(new Response("{}", { status: 201, headers: { "Content-Type": "application/json" } }));
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  });

  it("explains the need for a session when signed out", async () => {
    mount(false);
    expect(await screen.findByText(/Today needs a session/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Projects" }).getAttribute("href")).toBe("/projects");
  });

  it("renders the newest rows as labelled fields, never as JSON", async () => {
    mount(true, undefined, {
      operator: "o1",
      projects: [{
        project: "alpha", since: "2026-10-01T00:00:00", first_visit: false,
        changed: { counts: { acquire: 1 }, undated_rows: 0, newest: [
          { when: "2026-10-06T08:00:00", stage: "acquire",
            row: { source_id: "S-9", acquired: false, failure_class: "HTTP_403", note: "not named" } },
          { when: "2026-10-06T07:00:00", stage: "discover", row: { nothing: "known" } },
        ] },
        needs_you: { required: [], optional: [] }, continues_without_you: [],
      }],
    });
    const failure = await screen.findByText("HTTP_403");
    const line = failure.closest("li")!.textContent!;
    expect(line).toContain("source S-9");
    expect(line).toContain("acquired false");
    expect(line).toContain("failure class HTTP_403");
    expect(line).not.toContain("{");
    expect(line).not.toContain("not named");
    expect(screen.getByText("no field the portal names")).toBeTruthy();
  });

  it("names a failed Today read and says when no project is listed", async () => {
    mount(true, undefined, { error: { code: "INTERNAL", message: "today unreadable" } }, 500);
    expect(await screen.findByText("INTERNAL")).toBeTruthy();
    expect(screen.getByText("today unreadable")).toBeTruthy();
    cleanup();
    mount(true, undefined, { operator: "o1", projects: [] });
    expect(await screen.findByText("The server lists no project.")).toBeTruthy();
  });
});
