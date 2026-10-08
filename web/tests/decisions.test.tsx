// F5: the Decisions page. The open cards keep the server's order; the identity reason length
// is a client-side hint while the server's 422 is shown as given; the offer stage buttons are
// exactly those valid for the state and possession ("copy verified") is never a button; the
// retry preview renders the server's plan verbatim, refused hosts included. Signed out, the
// page offers the sign-in link and no write control.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import DecisionsPage from "@/pages/DecisionsPage";
import { SessionProvider } from "@/lib/session";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  });
}

const signedIn = () => json(200, { operator: { id: "ada", name: "Ada" }, csrf_token: "tok" });
const DECISIONS = "/control/v1/p/demo/flows/f1/decisions";
const RESOLVE = "/control/v1/p/demo/flows/f1/intake/in1/resolve";
const RETRY = "/control/v1/p/demo/flows/f1/decisions/retry-campaign";

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
    <MemoryRouter initialEntries={["/p/demo/f/f1/decisions"]}>
      <Routes>
        <Route
          path="/p/:project/f/:sel/decisions"
          element={<SessionProvider><DecisionsPage /></SessionProvider>}
        />
        <Route path="*" element={<div />} />
      </Routes>
    </MemoryRouter>,
  );
}

function identityOpen() {
  return {
    type: "identity", required: true, id: "in1", candidate_key: "s33",
    recorded_at: "2026-10-07T10:00:00+00:00",
    item: {
      intake_id: "in1", flow_id: "f1", kind: "reference", value: "Working paper 2017",
      submitted: "Working paper 2017", state: "POSSIBLE_VERSION", stage: "routing",
      reason: "the title matches a candidate in this flow",
      links: { candidate_key: "s33" }, recorded_at: "2026-10-07T10:00:00+00:00",
    },
  };
}

function offerOpen(id: string, state: string, possession: string | null, recordedAt: string) {
  return {
    type: "purchase_offer", required: false, id, candidate_key: "s14",
    recorded_at: recordedAt,
    item: {
      decision_id: id, kind: "purchase_offer", state, candidate_key: "s14",
      work_version: "journal version, 2018", vendor: "Example Press", price: "27.50",
      currency: "EUR", tax_status: null, terms_url: "https://example.com/terms",
      verified_at: "2026-10-06T09:12:00+00:00", resolves: "a copy would let its passages be read",
      possession, recorded_at: recordedAt,
    },
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("F5: Decisions page", () => {
  it("renders the open cards in the server's order, without re-sorting them", async () => {
    // An optional offer recorded before a required identity: sorting by required-first or by
    // age would flip them; the server's order stands.
    stub((url) => {
      if (url === "/control/v1/session") return signedIn();
      if (url === DECISIONS) {
        return json(200, {
          flow_id: "f1",
          open: [
            offerOpen("d2", "proposed", null, "2026-10-01T09:00:00+00:00"),
            identityOpen(),
          ],
          decided_recently: [{
            decision_id: "d0", kind: "retry_campaign", state: "declined",
            campaign: "retry-2026-09-30", recorded_at: "2026-10-01T08:00:00+00:00",
            reason: "the floor is already met; no request is worth making", until: null,
          }],
        });
      }
      return null;
    });
    const { container } = mount();
    await screen.findByLabelText("offer d2");
    const order = [...container.querySelectorAll("[data-open-id]")]
      .map((el) => el.getAttribute("data-open-id"));
    expect(order).toEqual(["d2", "in1"]);
    expect(await screen.findByText(/declined/)).toBeTruthy();
  });

  it("shows the reason hint for a non-not_sure answer, and the server's 422 as given", async () => {
    const refusal = "a reason of 3 characters is below 20: a decision another person will " +
      "read needs its grounds";
    stub((url, init) => {
      if (url === "/control/v1/session") return signedIn();
      if (url === DECISIONS) return json(200, { flow_id: "f1", open: [identityOpen()], decided_recently: [] });
      if (url === RESOLVE && init?.method === "POST") {
        return json(422, { error: { code: "VALIDATION", message: refusal } });
      }
      return null;
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Same work" }));
    expect(await screen.findByTestId("reason-hint")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your reason"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Record answer" }));
    expect(await screen.findByText("VALIDATION")).toBeTruthy();
    expect(screen.getByText(refusal)).toBeTruthy();
    const post = calls.find((c) => c.init?.method === "POST");
    expect(post?.url).toBe(RESOLVE);
    expect(JSON.parse(String(post?.init?.body))).toEqual({ answer: "same_work", reason: "abc" });
  });

  it("offers only the stage buttons valid for the offer's state, and copy verified is never a button", async () => {
    stub((url) => {
      if (url === "/control/v1/session") return signedIn();
      if (url === DECISIONS) {
        return json(200, {
          flow_id: "f1",
          open: [
            offerOpen("o1", "proposed", null, "2026-10-06T09:00:00+00:00"),
            offerOpen("o2", "approved", null, "2026-10-06T10:00:00+00:00"),
            offerOpen("o3", "bought_externally", "copy_verified", "2026-10-05T08:00:00+00:00"),
          ],
          decided_recently: [],
        });
      }
      return null;
    });
    mount();
    const proposed = await screen.findByLabelText("offer o1");
    expect(within(proposed).getByRole("button", { name: "Approve" })).toBeTruthy();
    expect(within(proposed).getByRole("button", { name: "Decline" })).toBeTruthy();
    expect(within(proposed).queryByRole("button", { name: "Bought externally" })).toBeNull();

    const approved = screen.getByLabelText("offer o2");
    expect(within(approved).queryByRole("button", { name: "Approve" })).toBeNull();
    expect(within(approved).getByRole("button", { name: "Bought externally" })).toBeTruthy();

    // bought_externally is terminal for a person: no stage buttons, no defer, no decline.
    const bought = screen.getByLabelText("offer o3");
    expect(within(bought).queryAllByRole("button")).toEqual([]);
    // Possession the server derived: a word on the card, never a control.
    expect(within(bought).getByText("copy_verified")).toBeTruthy();
    expect(screen.queryAllByRole("button", { name: /copy/i })).toEqual([]);
  });

  it("renders the retry preview verbatim, refused hosts included, then approves what was shown", async () => {
    const plan = {
      candidates: [{
        candidate_key: "s14", source_id: "S14", source_class: "journal",
        last_failure: "PAYWALL_403", hosts: ["a.example"],
      }],
      hosts: ["a.example"],
      refused_hosts: { "paywall.example": "excluded host for this project: never contacted" },
      robots: "honoured", max_requests_cap: 50,
      executes: "nothing: an approval is a record until an authorized operation names it",
    };
    stub((url, init) => {
      if (url === "/control/v1/session") return signedIn();
      if (url === DECISIONS) return json(200, { flow_id: "f1", open: [], decided_recently: [] });
      if (url.startsWith(`${RETRY}/preview`) && init?.method !== "POST") return json(200, plan);
      if (url === RETRY && init?.method === "POST") return json(201, { decision: {} });
      return null;
    });
    mount();
    fireEvent.change(await screen.findByLabelText("Candidate keys"),
      { target: { value: "s14 s31" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByTestId("retry-preview")).toBeTruthy();
    // The refused host and its sentence, verbatim.
    expect(screen.getByText("paywall.example")).toBeTruthy();
    expect(screen.getByText(/excluded host for this project: never contacted/)).toBeTruthy();
    expect(screen.getByText(plan.executes)).toBeTruthy();
    // Approve waits for a campaign name and a request ceiling, then sends what was previewed.
    const approve = screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: /Campaign name/ }),
      { target: { value: "retry-2026-10-07" } });
    fireEvent.change(screen.getByRole("textbox", { name: /Max requests/ }),
      { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => {
      const post = calls.find((c) => c.init?.method === "POST" && c.url === RETRY);
      expect(post).toBeDefined();
      expect(JSON.parse(String(post?.init?.body))).toEqual({
        candidate_ids: ["s14", "s31"], campaign: "retry-2026-10-07", max_requests: 6,
      });
    });
  });

  it("signed out shows Sign in to … and no write control", async () => {
    stub(() => json(401, { error: { code: "UNAUTHORIZED", message: "no session" } }));
    mount();
    expect(await screen.findByText(/Sign in to/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "record decisions" }).getAttribute("href"))
      .toBe("/login?next=%2Fp%2Fdemo%2Ff%2Ff1%2Fdecisions");
    // Only the session was probed: no control read was attempted without a session.
    expect(calls.map((c) => c.url)).toEqual(["/control/v1/session"]);
  });
});
