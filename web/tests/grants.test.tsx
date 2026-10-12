// The three grants on a series page, each separate: the calendar, the future copies, the local model.
// A grant sends exactly what the page shows, the page then reads again (no local "approved" flag), a
// changed plan is read again and never retried, and the server's refusal is shown as given.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import type { MandateStatus, PolicyStatus, ScheduleStatus } from "@/lib/scheduler";
import SeriesPage from "@/pages/SeriesPage";
import { expectNoPurchaseWording } from "./support/purchase";
import {
  authorized, err, indexPage, json, mandate, overviewOf, policy, schedule, SID, sent, stub,
} from "./support/schedulerFixtures";

vi.mock("@/hooks/usePoll", () => ({ usePoll: () => undefined }));

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

/** What the server holds, changed by the POST handlers; every GET answers from it. */
interface World { schedule: ScheduleStatus; policies: PolicyStatus[]; mandates: MandateStatus[] }
const world = (over: Partial<World> = {}): World => ({ schedule: schedule("PLANNED"), policies: [], mandates: [], ...over });

function serve(w: World, post: (url: string, body: unknown) => Promise<Response> | null = () => null, extra = {}) {
  return stub({
    schedule: () => json(200, w.schedule),
    indexFor: () => json(200, indexPage({ schedules: [w.schedule], copy_policies: w.policies, local_mandates: w.mandates })),
    policyRead: (id) => json(200, w.policies.find((p) => p.policy_id === id)),
    mandateRead: (id) => json(200, w.mandates.find((m) => m.mandate_id === id)),
    overview: () => json(200, overviewOf([], { ACADEMIC: {}, PREPRINT: {} })),
    post: (url, body) => post(url, body) ?? err(404, "NOT_FOUND", "no"),
    ...extra,
  });
}

const posts = () => sent.filter((c) => c.method === "POST");
const gets = (part: string) => sent.filter((c) => c.method === "GET" && c.url.includes(part));
const step = async (name: RegExp) => screen.findByRole("region", { name });
const SCHEDULE_URL = `/control/v1/p/news/schedules/${SID}`;

describe("Grants", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear(); });

  describe("the calendar", () => {
    it("PLANNED: the button waits for the box, sends exactly what is shown, then the page reads again", async () => {
      const w = world();
      serve(w, (url) => { if (url.endsWith("/authorize")) { w.schedule = schedule("AUTHORIZED", { events: [authorized()] }); return json(201, w.schedule); } return null; });
      mount();
      const calendar = await step(/Calendar/);
      expect(within(calendar).getByText("No request is permitted yet.")).toBeTruthy();
      expect(within(calendar).getByText(/480 requests/)).toBeTruthy();
      const button = within(calendar).getByRole("button", { name: "Authorize the calendar" });
      expect(button.hasAttribute("disabled")).toBe(true);
      fireEvent.click(within(calendar).getByRole("checkbox", { name: "I have read what this permits and its limits." }));
      expect(button.hasAttribute("disabled")).toBe(false);
      const before = gets("/schedules/").length;
      fireEvent.click(button);
      await waitFor(() => expect(posts()).toHaveLength(1));
      expect(posts()[0]).toMatchObject({ url: `${SCHEDULE_URL}/authorize`, body: { plan_sha256: SID, max_total_requests: 480 } });
      // no local "approved" flag: the page says Authorized only because it read the schedule again
      await waitFor(() => expect(gets("/schedules/").length).toBeGreaterThan(before));
      const idx = sent.findIndex((c) => c.method === "POST");
      expect(sent.slice(idx).some((c) => c.method === "GET" && c.url.startsWith(SCHEDULE_URL))).toBe(true);
      expect(await within(await step(/Calendar/)).findByText(/Bea Operator/)).toBeTruthy();
    });

    it("a double click sends one request", async () => {
      const w = world();
      let release: (r: Response) => void = () => undefined;
      serve(w, () => new Promise<Response>((resolve) => { release = resolve; }));
      mount();
      const calendar = await step(/Calendar/);
      fireEvent.click(within(calendar).getByRole("checkbox"));
      const button = within(calendar).getByRole("button", { name: "Authorize the calendar" });
      fireEvent.click(button);
      fireEvent.click(button);
      expect(posts()).toHaveLength(1);
      expect(within(calendar).getByRole("checkbox").hasAttribute("disabled")).toBe(true);
      await act(async () => { release(await json(201, schedule("AUTHORIZED"))); });
    });

    it("PLAN_DIFFERS clears the box, says so, reads again and does not retry", async () => {
      const w = world();
      serve(w, () => err(409, "PLAN_DIFFERS", "schedule hash or request ceiling changed"));
      mount();
      const calendar = await step(/Calendar/);
      const box = within(calendar).getByRole("checkbox") as HTMLInputElement;
      fireEvent.click(box);
      const before = gets("/schedules/").length;
      fireEvent.click(within(calendar).getByRole("button", { name: "Authorize the calendar" }));
      expect(await within(calendar).findByText("The plan changed after you opened this page; it has been reloaded below. Read it again before deciding.")).toBeTruthy();
      expect((within(calendar).getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
      await waitFor(() => expect(gets("/schedules/").length).toBeGreaterThan(before));
      await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
      expect(posts()).toHaveLength(1);
    });

    it("a refusal is shown as the server wrote it", async () => {
      serve(world(), () => err(409, "REFUSED", "a schedule window expired before authorization"));
      mount();
      const calendar = await step(/Calendar/);
      fireEvent.click(within(calendar).getByRole("checkbox"));
      fireEvent.click(within(calendar).getByRole("button", { name: "Authorize the calendar" }));
      const alert = await within(calendar).findByRole("alert");
      expect(alert.textContent).toContain("a schedule window expired before authorization");
      expect(document.activeElement).toBe(alert);
    });

    it("AUTHORIZED: who and when, and Revoke sends only the plan hash", async () => {
      const w = world({ schedule: schedule("AUTHORIZED", { events: [{ event: "authorized", at: "2026-10-01T09:30:00+00:00", identity: { uid: 1000, login: "stefano" } }] }) });
      serve(w, () => json(200, schedule("REVOKED")));
      mount();
      const calendar = await step(/Calendar/);
      expect(within(calendar).getByText(/stefano/)).toBeTruthy();
      expect(within(calendar).getByText("Stops later starts. A search already running finishes.")).toBeTruthy();
      fireEvent.click(within(calendar).getByRole("checkbox"));
      fireEvent.click(within(calendar).getByRole("button", { name: "Revoke the calendar" }));
      await waitFor(() => expect(posts()).toHaveLength(1));
      expect(posts()[0]).toMatchObject({ url: `${SCHEDULE_URL}/revoke`, body: { plan_sha256: SID } });
    });

    it("REVOKED: who and when, no action, and the note that it cannot be authorized again", async () => {
      serve(world({ schedule: schedule("REVOKED", { events: [authorized(), { event: "revoked", at: "2026-10-05T09:30:00+00:00", identity: { operator: "cy", name: "Cy Off" } }] }) }));
      mount();
      const calendar = await step(/Calendar/);
      expect(within(calendar).getByText(/Cy Off/)).toBeTruthy();
      expect(within(calendar).queryByRole("button")).toBeNull();
      expect(within(calendar).getByText("A revoked schedule cannot be authorized again; plan a new series.")).toBeTruthy();
    });
  });

  describe("the future copies", () => {
    const opened = async (w = world({ schedule: schedule("AUTHORIZED") }), post?: Parameters<typeof serve>[1]) => {
      serve(w, post);
      mount();
      const step3 = await step(/Future copies/);
      await within(step3).findByText("Not decided.");
      fireEvent.click(within(step3).getByRole("button", { name: "Plan a copy policy" }));
      return step3;
    };

    it("offers a form with no default hosts, the window of the schedule, class suggestions and a live product", async () => {
      const step3 = await opened();
      expect((within(step3).getByLabelText(/^Hosts copies may come from/) as HTMLTextAreaElement).value).toBe("");
      expect(document.activeElement).toBe(within(step3).getByLabelText(/^Hosts copies may come from/));
      expect((within(step3).getByLabelText("Starts (UTC)") as HTMLInputElement).value).toBe("2025-01-01T00:00:00+00:00");
      expect((within(step3).getByLabelText("Ends (UTC)") as HTMLInputElement).value).toBe("2025-02-28T00:00:00+00:00");
      await within(step3).findByRole("checkbox", { name: "ACADEMIC" });
      expect(within(step3).getByRole("checkbox", { name: "PREPRINT" })).toBeTruthy();
      fireEvent.change(within(step3).getByLabelText("Candidates, at most"), { target: { value: "10" } });
      fireEvent.change(within(step3).getByLabelText("Requests per candidate, at most"), { target: { value: "3" } });
      expect(within(step3).getByText("Ceiling: 10 × 3 = 30 requests")).toBeTruthy();
      expect(within(step3).getByText("Planning permits nothing: no request is made until you authorize the policy.")).toBeTruthy();
    });

    it("plans with exactly the seven keys: hosts split and lowercased, classes sorted, numbers as numbers", async () => {
      const w = world({ schedule: schedule("AUTHORIZED") });
      const step3 = await opened(w, (url) => {
        if (url.endsWith("/copy-policies")) { w.policies = [policy("PLANNED", SID)]; return json(201, w.policies[0]); }
        return null;
      });
      fireEvent.change(within(step3).getByLabelText(/^Hosts copies may come from/), { target: { value: " Europepmc.ORG \n\narxiv.org " } });
      fireEvent.click(await within(step3).findByRole("checkbox", { name: "PREPRINT" }));
      fireEvent.click(within(step3).getByRole("checkbox", { name: "ACADEMIC" }));
      fireEvent.change(within(step3).getByLabelText("Other class ids (comma separated)"), { target: { value: "ZETA, beta" } });
      fireEvent.change(within(step3).getByLabelText("Candidates, at most"), { target: { value: "10" } });
      fireEvent.change(within(step3).getByLabelText("Requests per candidate, at most"), { target: { value: "3" } });
      const walks = gets("scheduler?limit=100").length;
      fireEvent.click(within(step3).getByRole("button", { name: "Save the policy" }));
      await waitFor(() => expect(posts()).toHaveLength(1));
      expect(posts()[0]).toMatchObject({ url: "/control/v1/p/news/copy-policies", body: {
        schedule_id: SID, allowed_hosts: ["europepmc.org", "arxiv.org"], source_classes: ["ACADEMIC", "PREPRINT", "ZETA", "beta"].sort(),
        max_candidates: 10, max_requests_each: 3,
        not_before: "2025-01-01T00:00:00+00:00", expires_at: "2025-02-28T00:00:00+00:00" } });
      expect(Object.keys(posts()[0].body as object).sort()).toEqual(["allowed_hosts", "expires_at", "max_candidates", "max_requests_each", "not_before", "schedule_id", "source_classes"]);
      // a new policy has an id the page did not know: the index is walked again
      await waitFor(() => expect(gets("scheduler?limit=100").length).toBeGreaterThan(walks));
      expect(await within(await step(/Future copies/)).findByRole("button", { name: "Authorize the copy policy" })).toBeTruthy();
    });

    it("shows the server's refusal as given and keeps every value", async () => {
      const step3 = await opened(undefined, () => err(409, "REFUSED", "copy policy needs declared source classes"));
      fireEvent.change(within(step3).getByLabelText(/^Hosts copies may come from/), { target: { value: "arxiv.org" } });
      fireEvent.change(within(step3).getByLabelText("Other class ids (comma separated)"), { target: { value: "UNDECLARED" } });
      fireEvent.change(within(step3).getByLabelText("Candidates, at most"), { target: { value: "7" } });
      fireEvent.change(within(step3).getByLabelText("Requests per candidate, at most"), { target: { value: "2" } });
      fireEvent.click(within(step3).getByRole("button", { name: "Save the policy" }));
      const alert = await within(step3).findByRole("alert");
      expect(alert.textContent).toContain("copy policy needs declared source classes");
      expect((within(step3).getByLabelText(/^Hosts copies may come from/) as HTMLTextAreaElement).value).toBe("arxiv.org");
      expect((within(step3).getByLabelText("Candidates, at most") as HTMLInputElement).value).toBe("7");
      expect((within(step3).getByLabelText("Other class ids (comma separated)") as HTMLInputElement).value).toBe("UNDECLARED");
      expect(document.activeElement).toBe(alert);
    });

    it("will not send without a host, a class and caps in range, and says which is missing", async () => {
      const step3 = await opened();
      const save = () => within(step3).getByRole("button", { name: "Save the policy" });
      expect(save().hasAttribute("disabled")).toBe(true);
      expect(within(step3).getByText("Name at least one host.")).toBeTruthy();
      fireEvent.change(within(step3).getByLabelText(/^Hosts copies may come from/), { target: { value: "arxiv.org" } });
      expect(within(step3).getByText("Choose at least one source class.")).toBeTruthy();
      fireEvent.change(within(step3).getByLabelText("Other class ids (comma separated)"), { target: { value: "ACADEMIC" } });
      fireEvent.change(within(step3).getByLabelText("Candidates, at most"), { target: { value: "5000" } });
      fireEvent.change(within(step3).getByLabelText("Requests per candidate, at most"), { target: { value: "3" } });
      expect(within(step3).getByText("Candidates: 1 to 1000. Requests per candidate: 1 to 20.")).toBeTruthy();
      expect(save().hasAttribute("disabled")).toBe(true);
      fireEvent.change(within(step3).getByLabelText("Candidates, at most"), { target: { value: "50" } });
      expect(save().hasAttribute("disabled")).toBe(false);
    });

    it("hides the create form while the schedule is REVOKED", async () => {
      serve(world({ schedule: schedule("REVOKED") }));
      mount();
      const step3 = await step(/Future copies/);
      await within(step3).findByText("Not decided.");
      expect(within(step3).queryByRole("button", { name: "Plan a copy policy" })).toBeNull();
    });

    it("a frozen policy: Authorize sends the displayed values; a changed plan is read again, not retried", async () => {
      const p = policy("PLANNED", SID, { policy_id: "p".repeat(64) });
      const w = world({ schedule: schedule("AUTHORIZED"), policies: [p] });
      serve(w, () => err(409, "PLAN_DIFFERS", "copy policy hash or limits changed"));
      mount();
      const step3 = await step(/Future copies/);
      await within(step3).findByText(/europepmc\.org/);
      expect(within(step3).getByText("Planned only: nothing is permitted until you authorize it.")).toBeTruthy();
      fireEvent.click(within(step3).getByRole("checkbox"));
      fireEvent.click(within(step3).getByRole("button", { name: "Authorize the copy policy" }));
      await waitFor(() => expect(posts()).toHaveLength(1));
      expect(posts()[0]).toMatchObject({ url: `/control/v1/p/news/copy-policies/${"p".repeat(64)}/authorize`,
        body: { policy_sha256: "p".repeat(64), max_candidates: 10, max_requests_each: 3, max_total_requests: 30 } });
      expect(await within(step3).findByText(/The plan changed after you opened this page/)).toBeTruthy();
      expect(gets(`/copy-policies/${"p".repeat(64)}`).length).toBeGreaterThan(0);
      expect(posts()).toHaveLength(1);
    });

    it("an authorized policy shows its reservations and Revoke sends only the hash", async () => {
      const p = policy("AUTHORIZED", SID, { reserved_candidates: 4, reserved_requests: 9 });
      serve(world({ schedule: schedule("AUTHORIZED"), policies: [p] }), () => json(200, { ...p, state: "REVOKED" }));
      mount();
      const step3 = await step(/Future copies/);
      expect(await within(step3).findByText("Candidates reserved: 4 / 10")).toBeTruthy();
      expect(within(step3).getByText("Requests reserved: 9")).toBeTruthy();
      fireEvent.click(within(step3).getByRole("checkbox"));
      fireEvent.click(within(step3).getByRole("button", { name: "Revoke the copy policy" }));
      await waitFor(() => expect(posts()).toHaveLength(1));
      expect(posts()[0]).toMatchObject({ url: `/control/v1/p/news/copy-policies/${"p".repeat(64)}/revoke`, body: { policy_sha256: "p".repeat(64) } });
    });

    it("several policies each carry their own state and their own action", async () => {
      const a = policy("PLANNED", SID, { policy_id: "1".repeat(64) });
      const b = policy("AUTHORIZED", SID, { policy_id: "2".repeat(64) });
      const c = policy("REVOKED", SID, { policy_id: "3".repeat(64) });
      serve(world({ schedule: schedule("AUTHORIZED"), policies: [a, b, c] }));
      mount();
      const step3 = await step(/Future copies/);
      await within(step3).findAllByText(/europepmc\.org/);
      const rows = within(step3).getAllByRole("group", { name: /^Copy policy / });
      expect(rows).toHaveLength(3);
      expect(within(rows[0]).getByTitle("PLANNED")).toBeTruthy();
      expect(within(rows[0]).getByRole("button", { name: "Authorize the copy policy" })).toBeTruthy();
      expect(within(rows[1]).getByTitle("AUTHORIZED")).toBeTruthy();
      expect(within(rows[1]).getByRole("button", { name: "Revoke the copy policy" })).toBeTruthy();
      expect(within(rows[2]).getByTitle("REVOKED")).toBeTruthy();
      expect(within(rows[2]).queryByRole("button")).toBeNull();
    });
  });

  describe("the local model", () => {
    const opened = async (w = world({ schedule: schedule("AUTHORIZED") }), post?: Parameters<typeof serve>[1]) => {
      serve(w, post);
      mount();
      const step4 = await step(/Local model/);
      await within(step4).findByText("Not decided.");
      fireEvent.click(within(step4).getByRole("button", { name: "Enable a local model" }));
      return step4;
    };

    it("sends the schedule's flows in order, never typed, with two distinct models and a positive cap", async () => {
      const w = world({ schedule: schedule("AUTHORIZED") });
      const step4 = await opened(w, (url) => { if (url.endsWith("/local-mandates/series")) { w.mandates = [mandate("ENABLED", SID)]; return json(201, w.mandates[0]); } return null; });
      expect(document.activeElement).toBe(within(step4).getByLabelText("Model for extraction"));
      fireEvent.change(within(step4).getByLabelText("Model for extraction"), { target: { value: "qwen-a" } });
      fireEvent.change(within(step4).getByLabelText("Model for review"), { target: { value: "qwen-a" } });
      fireEvent.change(within(step4).getByLabelText("Local calls, at most"), { target: { value: "200" } });
      expect(within(step4).getByText("The two models must be different.")).toBeTruthy();
      fireEvent.click(within(step4).getByRole("checkbox"));
      expect(within(step4).getByRole("button", { name: "Enable the local model" }).hasAttribute("disabled")).toBe(true);
      fireEvent.change(within(step4).getByLabelText("Model for review"), { target: { value: "qwen-b" } });
      expect(within(step4).getByRole("button", { name: "Enable the local model" }).hasAttribute("disabled")).toBe(false);
      const walks = gets("scheduler?limit=100").length;
      fireEvent.click(within(step4).getByRole("button", { name: "Enable the local model" }));
      await waitFor(() => expect(posts()).toHaveLength(1));
      expect(posts()[0]).toMatchObject({ url: "/control/v1/p/news/local-mandates/series",
        body: { schedule_id: SID, flow_ids: ["flow1", "flow2"], extract_model: "qwen-a", review_model: "qwen-b", max_total_local_calls: 200 } });
      expect(Object.keys(posts()[0].body as object).sort()).toEqual(["extract_model", "flow_ids", "max_total_local_calls", "review_model", "schedule_id"]);
      await waitFor(() => expect(gets("scheduler?limit=100").length).toBeGreaterThan(walks));
    });

    it("needs an authorized calendar first", async () => {
      serve(world());
      mount();
      const step4 = await step(/Local model/);
      await within(step4).findByText("Not decided.");
      expect(within(step4).queryByRole("button", { name: "Enable a local model" })).toBeNull();
      expect(within(step4).getByText("Authorize the calendar first; a local model can be enabled only for an authorized calendar.")).toBeTruthy();
    });

    it("a changed flow list is read again, not retried", async () => {
      const step4 = await opened(undefined, () => err(409, "PLAN_DIFFERS", "schedule child flows changed"));
      fireEvent.change(within(step4).getByLabelText("Model for extraction"), { target: { value: "a" } });
      fireEvent.change(within(step4).getByLabelText("Model for review"), { target: { value: "b" } });
      fireEvent.change(within(step4).getByLabelText("Local calls, at most"), { target: { value: "5" } });
      fireEvent.click(within(step4).getByRole("checkbox"));
      fireEvent.click(within(step4).getByRole("button", { name: "Enable the local model" }));
      expect(await within(step4).findByText(/The plan changed after you opened this page/)).toBeTruthy();
      expect(posts()).toHaveLength(1);
    });

    it("rows: each mandate has its own state; Disable sends only the mandate id; a disabled one has no action", async () => {
      const on = mandate("ENABLED", SID, { mandate_id: "a".repeat(64) });
      const off = mandate("DISABLED", SID, { mandate_id: "b".repeat(64), disabled_by: { uid: 1000, login: "stefano" } });
      serve(world({ schedule: schedule("AUTHORIZED"), mandates: [on, off] }), () => json(200, { ...on, state: "DISABLED" }));
      mount();
      const step4 = await step(/Local model/);
      const rows = await within(step4).findAllByRole("group", { name: /^Local model / });
      expect(rows).toHaveLength(2);
      expect(within(rows[0]).getByTitle("ENABLED")).toBeTruthy();
      expect(within(rows[1]).getByTitle("DISABLED")).toBeTruthy();
      expect(within(rows[1]).queryByRole("button")).toBeNull();
      expect(within(rows[0]).getByText("Disabling stops later passes; a call already running is not undone.")).toBeTruthy();
      fireEvent.click(within(rows[0]).getByRole("checkbox"));
      fireEvent.click(within(rows[0]).getByRole("button", { name: "Disable the local model" }));
      await waitFor(() => expect(posts()).toHaveLength(1));
      expect(posts()[0]).toMatchObject({ url: `/control/v1/p/news/local-mandates/${"a".repeat(64)}/disable`, body: { mandate_id: "a".repeat(64) } });
      // an enabled mandate means no second one is offered
      expect(within(step4).queryByRole("button", { name: "Enable a local model" })).toBeNull();
    });
  });

  describe("texts", () => {
    it("the explanations keep to the verified clauses and offer no purchase, forms open or closed", async () => {
      const w = world({ schedule: schedule("AUTHORIZED") });
      serve(w);
      mount();
      const step3 = await step(/Future copies/);
      await within(step3).findByText("Not decided.");
      fireEvent.click(within(step3).getByRole("button", { name: "Plan a copy policy" }));
      fireEvent.click(within(await step(/Local model/)).getByRole("button", { name: "Enable a local model" }));
      expectNoPurchaseWording(document.body.textContent!, "en", ["sched.policy.forbids", "sched.mandate.forbids"]);
    });

    it("renders in Italian, forms included, with no purchase wording", async () => {
      localStorage.setItem(STORAGE_KEY, "it");
      const w = world({ schedule: schedule("PLANNED", {}), policies: [policy("PLANNED", SID)] });
      serve(w);
      mount();
      const calendar = await step(/Calendario/);
      expect(within(calendar).getByRole("button", { name: "Autorizza il calendario" })).toBeTruthy();
      expect(within(calendar).getByRole("checkbox", { name: "Ho letto cosa permette e i suoi limiti." })).toBeTruthy();
      const step3 = await step(/Copie future/);
      expect(await within(step3).findByRole("button", { name: "Autorizza la regola per le copie" })).toBeTruthy();
      fireEvent.click(within(step3).getByRole("button", { name: "Pianifica una regola per le copie" }));
      expect(within(step3).getByLabelText(/^Host da cui possono arrivare le copie/)).toBeTruthy();
      expectNoPurchaseWording(document.body.textContent!, "it", ["sched.policy.forbids", "sched.mandate.forbids"]);
    });
  });
});
