// The three grants on a series page, each separate: the calendar, the future copies, the local model.
// A grant sends exactly what the page shows, the page then reads again (no local "approved" flag), a
// changed plan is read again and never retried, and the server's refusal is shown as given.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import type { MandateStatus, PolicyStatus, ScheduleStatus } from "@/lib/scheduler";
import SeriesPage from "@/pages/SeriesPage";
import {
  authorized, err, indexPage, json, overviewOf, schedule, SID, sent, stub,
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
});
