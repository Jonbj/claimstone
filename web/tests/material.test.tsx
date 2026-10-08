// F5: the Add material page. The client refuses a file over 50 MiB before anything is sent;
// a POSSIBLE_VERSION item links to this flow's Decisions; a proposal's answer row shows the
// server's own state and reason. Signed out, the page offers the sign-in link and no write
// control.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import MaterialPage from "@/pages/MaterialPage";
import { SessionProvider } from "@/lib/session";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  });
}

const signedIn = () => json(200, { operator: { id: "ada", name: "Ada" }, csrf_token: "tok" });
const INTAKE = "/control/v1/p/demo/flows/f1/intake";
const OVERVIEW = "/api/v1/projects/demo/flows/f1/overview";

type Call = { url: string; init?: RequestInit };
let calls: Call[] = [];

function stub(handler: (url: string, init?: RequestInit) => Response | null) {
  calls = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const answer = handler(url, init);
    return Promise.resolve(
      answer ?? json(404, { error: { code: "NOT_FOUND", message: `no stub for ${url}` } }));
  });
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/p/demo/f/f1/material"]}>
      <Routes>
        <Route
          path="/p/:project/f/:sel/material"
          element={<SessionProvider><MaterialPage /></SessionProvider>}
        />
        <Route path="*" element={<div />} />
      </Routes>
    </MemoryRouter>,
  );
}

const OVERVIEW_BODY = {
  api_version: 1, project: "demo", selector: { round: "r1", manifest_only: false },
  selector_label: "r1", legacy: false, errors: [], unavailable: "", activity: [],
  binding_state: null, flow: null, inbox: [], questions: { project: "demo", round: "r1", rows: [] },
  question_state_counts: {
    awaiting_a_person: 0, historical: 0, no_profile: 0, no_verified_claim: 0,
    not_applicable: 0, provisional: 0, signed: 0, stale: 0,
  },
  source_tracker: [
    { candidate_key: "s23", source_id: "S23", source_class: "journal", state: "not_obtained",
      tooltip: "not obtained: paywall refused" },
    { candidate_key: "s31", source_id: "S31", source_class: "working_paper", state: "confirmed",
      tooltip: "obtained and confirmed as a document by normalize" },
  ],
  state: { errors: [], floor: null, project: "demo", questions: [], rejections_by_reason: {},
    round: "r1", stages: [], unavailable: "", verdicts_recorded: 0, verdicts_stale: 0 },
};

const POSSIBLE_ITEM = {
  intake_id: "i1", flow_id: "f1", kind: "reference", value: "Working paper 2017",
  submitted: "Working paper 2017", state: "POSSIBLE_VERSION", stage: "routing",
  reason: "the title matches a candidate in this flow",
  links: { candidate_key: "s12" }, recorded_at: "2026-10-06T10:12:00+00:00",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("F5: Add material page", () => {
  it("signed out shows Sign in to … and no write control", async () => {
    stub(() => json(401, { error: { code: "UNAUTHORIZED", message: "no session" } }));
    mount();
    expect(await screen.findByText(/Sign in to/)).toBeTruthy();
    const href = screen.getByRole("link", { name: "add material" }).getAttribute("href");
    expect(href).toBe("/login?next=%2Fp%2Fdemo%2Ff%2Ff1%2Fmaterial");
    expect(calls.map((c) => c.url)).toEqual(["/control/v1/session"]);
  });

  it("shows the proposal's answer row with the server's state and reason", async () => {
    const row = {
      intake_id: "i9", kind: "reference", value: "Working paper 2017",
      submitted: "Working paper 2017", state: "READY", stage: "routing",
      reason: "routed to round r1's next discover, which applies the round's population predicate",
      links: {}, recorded_at: "2026-10-07T11:00:00+00:00",
    };
    stub((url, init) => {
      if (url === "/control/v1/session") return signedIn();
      if (url === OVERVIEW) return json(200, OVERVIEW_BODY);
      if (url === INTAKE && init?.method !== "POST") return json(200, { flow_id: "f1", items: [] });
      if (url === INTAKE && init?.method === "POST") return json(201, { intake: row });
      return null;
    });
    mount();
    fireEvent.change(await screen.findByLabelText("Value"),
      { target: { value: "Working paper 2017" } });
    fireEvent.click(screen.getByRole("button", { name: "Propose" }));
    expect(await screen.findByTestId("propose-result")).toBeTruthy();
    expect(screen.getByText("READY")).toBeTruthy();
    expect(screen.getByText(row.reason)).toBeTruthy();
    const post = calls.find((c) => c.init?.method === "POST");
    expect(post?.url).toBe(INTAKE);
    expect(JSON.parse(String(post?.init?.body)))
      .toEqual({ kind: "reference", value: "Working paper 2017" });
  });

  it("refuses a file over 50 MiB before sending anything", async () => {
    let xhrConstructed = false;
    class TrapXhr {
      constructor() {
        xhrConstructed = true;
      }
    }
    vi.stubGlobal("XMLHttpRequest", TrapXhr);
    stub((url) => {
      if (url === "/control/v1/session") return signedIn();
      if (url === OVERVIEW) return json(200, OVERVIEW_BODY);
      if (url === INTAKE) return json(200, { flow_id: "f1", items: [] });
      return null;
    });
    mount();
    await screen.findByRole("combobox", { name: /Target candidate/ });
    fireEvent.change(screen.getByRole("combobox", { name: /Target candidate/ }),
      { target: { value: "s23" } });
    const big = new File(["x"], "big.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 50 * 1024 * 1024 + 1 });
    const picker = screen.getByLabelText("PDF");
    Object.defineProperty(picker, "files", { value: [big] });
    fireEvent.change(picker);
    expect(await screen.findByText("TOO_LARGE")).toBeTruthy();
    expect(screen.getByText(/a file must be at most 50 MiB/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Upload" }) as HTMLButtonElement).disabled)
      .toBe(true);
    expect(xhrConstructed).toBe(false);
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);
  });

  it("links a POSSIBLE_VERSION item to Decisions", async () => {
    stub((url) => {
      if (url === "/control/v1/session") return signedIn();
      if (url === OVERVIEW) return json(200, OVERVIEW_BODY);
      if (url === INTAKE) return json(200, { flow_id: "f1", items: [POSSIBLE_ITEM] });
      return null;
    });
    mount();
    const link = await screen.findByTestId("identity-link");
    expect(link.getAttribute("href")).toBe("/p/demo/f/f1/decisions");
    expect(link.textContent).toBe("Decisions");
    expect(screen.getByText(POSSIBLE_ITEM.reason)).toBeTruthy();
  });
});
