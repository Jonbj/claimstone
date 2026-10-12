// The cumulative result page (read-only): the dossier's state and blockers, the acquisition
// figures with their denominators, the questions (profiles joined to human decisions by question
// id), and the live-JSON download. It gives no verdict, and a malformed audit is "not available",
// never a throw.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import CumulativeResultPage from "@/pages/CumulativeResultPage";
import {
  admission, decision, err, json, profile, resultDossier, SHA, SID, stub,
} from "./support/schedulerFixtures";

let firePoll: () => void = () => undefined;
vi.mock("@/hooks/usePoll", () => ({
  usePoll: (_project: string | null, onChange: () => void) => { firePoll = onChange; },
}));

function mount() {
  render(
    <MemoryRouter initialEntries={[`/p/news/scheduler/s/${SID}/result`]}>
      <LocaleProvider>
        <SessionProvider>
          <Routes><Route path="/p/:project/scheduler/s/:schedule/result" element={<CumulativeResultPage />} /></Routes>
        </SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

const readBlob = (blob: Blob) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result));
  reader.onerror = () => reject(reader.error);
  reader.readAsText(blob);
});

const served = (body: unknown) => ({ dossier: () => json(200, body) });

describe("Cumulative result page", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

  it("shows the dossier state (label visible, server word in the title), every blocker verbatim, and no verdict", async () => {
    stub(served(resultDossier({ state: "WAITING_FOR_EVIDENCE",
      blockers: ["INCOMPLETE_CUMULATIVE_EVIDENCE", "NO_ADMISSIBLE_PROFILE"] })));
    mount();
    const banner = await screen.findByRole("region", { name: "Dossier" });
    const word = within(banner).getByTitle("WAITING_FOR_EVIDENCE");
    expect(word.textContent).toBe("Waiting for evidence");
    expect(within(banner).getByText("INCOMPLETE_CUMULATIVE_EVIDENCE")).toBeTruthy();
    expect(within(banner).getByText("NO_ADMISSIBLE_PROFILE")).toBeTruthy();
    expect(within(banner).getByText(/gives no verdict/)).toBeTruthy();
  });

  it("an unknown dossier state is shown as sent", async () => {
    stub(served(resultDossier({ state: "SOMETHING_NEW" })));
    mount();
    expect((await screen.findByTitle("SOMETHING_NEW")).textContent).toBe("SOMETHING_NEW");
  });

  it("the cumulative acquisition keeps found in the denominator and names classes below the floor", async () => {
    stub(served(resultDossier({}, {
      cumulative_admission: admission({ found: 40, confirmed: 12, obtained: 15, rate: 0.375, floor: 0.8,
        status: "INSUFFICIENT_ACQUISITION", classes_below_floor: ["PREPRINT"],
        by_class: { PREPRINT: { rate: 0.2, floor: 0.5, meets_floor: false } } }),
    })));
    mount();
    const panel = await screen.findByRole("region", { name: "Acquisition" });
    expect(within(panel).getByText("12 / 40")).toBeTruthy();
    expect(within(panel).getByText("INSUFFICIENT_ACQUISITION", { selector: "b" })).toBeTruthy();
    expect(within(panel).getAllByText(/37\.5%/).length).toBeGreaterThan(0);
    expect(within(panel).getByText("Classes below the floor: PREPRINT")).toBeTruthy();
    // per round, in the same shape
    expect(within(panel).getByText("3 / 8")).toBeTruthy();
    expect(within(panel).getByText("0 / 0")).toBeTruthy();
  });

  it("a malformed audit says not available and does not throw; the questions still render", async () => {
    stub(served(resultDossier({ profiles: [profile("q1")] }, { cumulative_admission: "garbage", rounds: 7 })));
    mount();
    const panel = await screen.findByRole("region", { name: "Acquisition" });
    expect(within(panel).getByText("Not available.")).toBeTruthy();
    expect(screen.getByRole("row", { name: /q1/ })).toBeTruthy();
  });

  it("joins profiles and decisions by question id; a decision without a profile still shows", async () => {
    stub(served(resultDossier({
      profiles: [profile("q1"), profile("q2", { provisional: true })],
      human_decisions: [decision("q1", { verdict: { verdict: "SUPPORTED" } }), decision("q2"), decision("q9")],
    })));
    mount();
    const q1 = await screen.findByRole("row", { name: /q1/ });
    expect(within(q1).getByText("SUPPORTED")).toBeTruthy();
    expect(within(q1).getByText(/yes: 4/)).toBeTruthy();
    expect(within(q1).getByText(/10 \/ 12/)).toBeTruthy();
    const q2 = screen.getByRole("row", { name: /q2/ });
    expect(within(q2).getByText("not signed")).toBeTruthy();
    expect(within(q2).getByText("provisional")).toBeTruthy();
    const q9 = screen.getByRole("row", { name: /q9/ });
    expect(within(q9).getByText("no profile")).toBeTruthy();
    expect(within(q9).getByText("not signed")).toBeTruthy();
  });

  it("shortens the profile hash with a copy button; shows the stale marker and the unavailable string verbatim", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    stub(served(resultDossier({
      profiles: [profile("q1", { profile_sha256: SHA("d") })],
      human_decisions: [decision("q1", { stored_profile_stale: true, unavailable: "REGISTRY_DRIFT: ask again" })],
    })));
    mount();
    const row = await screen.findByRole("row", { name: /q1/ });
    expect(within(row).getByText("dddddddddddd")).toBeTruthy();
    fireEvent.click(within(row).getByRole("button", { name: /Copy/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SHA("d")));
    expect(within(row).getByText("stale")).toBeTruthy();
    expect(within(row).getByText("REGISTRY_DRIFT: ask again")).toBeTruthy();
  });

  it("an operational question reads 'no literature verdict applies'", async () => {
    stub(served(resultDossier({
      profiles: [{ question_id: "op1", kind: "operational", state: "LITERATURE_VERDICT_NOT_APPLICABLE", reason: "r", see: [] }],
      human_decisions: [decision("op1")],
    })));
    mount();
    const row = await screen.findByRole("row", { name: /op1/ });
    expect(within(row).getByText("no literature verdict applies")).toBeTruthy();
  });

  it("links a question to the whole-store reader only when the project lists the '-' selector", async () => {
    const body = resultDossier({ profiles: [profile("q1")], human_decisions: [decision("q1")] });
    stub({ ...served(body), unbound: ["-"] });
    mount();
    const link = await screen.findByRole("link", { name: "q1" });
    expect(link.getAttribute("href")).toBe("/p/news/u/-/q/q1");
    cleanup();
    stub({ ...served(body), unbound: ["r0"] });
    mount();
    const row = await screen.findByRole("row", { name: /q1/ });
    expect(within(row).queryByRole("link", { name: "q1" })).toBeNull();
    expect(within(row).getByText("q1")).toBeTruthy();
  });

  it("says under the questions that signing is per flow", async () => {
    stub(served(resultDossier()));
    mount();
    expect(await screen.findByText(/Signing in the portal is per flow, on that flow's own profile/)).toBeTruthy();
  });

  describe("download", () => {
    let created: Blob[];
    let revoked: string[];
    let clicked: Array<{ download: string; href: string }>;
    beforeEach(() => {
      created = []; revoked = []; clicked = [];
      URL.createObjectURL = vi.fn((blob: Blob) => { created.push(blob); return "blob:live-1"; });
      URL.revokeObjectURL = vi.fn((url: string) => { revoked.push(url); });
      vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push({ download: this.download, href: this.href });
      });
    });
    afterEach(() => vi.restoreAllMocks());

    it("hands over the exact fetched payload as a file, with no extra request, and revokes the URL", async () => {
      const body = resultDossier({ profiles: [profile("q1")] });
      const urls = stub(served(body));
      mount();
      const button = await screen.findByRole("button", { name: "Download live report (JSON)" });
      const before = urls.length;
      fireEvent.click(button);
      expect(urls.length).toBe(before);
      expect(created).toHaveLength(1);
      expect(JSON.parse(await readBlob(created[0]))).toEqual(body);
      expect(clicked).toHaveLength(1);
      expect(clicked[0].download).toMatch(/\.json$/);
      expect(clicked[0].href).toBe("blob:live-1");
      expect(revoked).toEqual(["blob:live-1"]);
    });

    it("is a 'current saved dossier' only when finalized and not stale", async () => {
      stub(served(resultDossier({ finalized_dossier_id: SHA("f"), snapshot_stale: false })));
      mount();
      expect(await screen.findByRole("button", { name: "Download current saved dossier (JSON)" })).toBeTruthy();
      cleanup();
      stub(served(resultDossier({ finalized_dossier_id: SHA("f"), snapshot_stale: true })));
      mount();
      expect(await screen.findByRole("button", { name: "Download live report (JSON)" })).toBeTruthy();
      cleanup();
      stub(served(resultDossier({ finalized_dossier_id: null, snapshot_stale: false })));
      mount();
      expect(await screen.findByRole("button", { name: "Download live report (JSON)" })).toBeTruthy();
    });

    it("offers no verified-package button", async () => {
      stub(served(resultDossier()));
      mount();
      await screen.findByRole("button", { name: /Download/ });
      expect(screen.queryByRole("button", { name: /package/i })).toBeNull();
    });
  });

  it("reads the dossier once on load and again only when the poll fires", async () => {
    const urls = stub(served(resultDossier()));
    mount();
    await screen.findByRole("region", { name: "Dossier" });
    const reads = () => urls.filter((u) => u.includes("periodic-dossiers")).length;
    expect(reads()).toBe(1);
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(reads()).toBe(1);
    await act(async () => { firePoll(); });
    await waitFor(() => expect(reads()).toBe(2));
  });

  it("a failing read is a named blocking state, never an empty page", async () => {
    stub({ dossier: () => err(409, "REGISTRY_DRIFT", "the registry changed under its version") });
    mount();
    const banner = await screen.findByRole("alert");
    expect(banner.textContent).toContain("REGISTRY_DRIFT");
    expect(banner.textContent).toContain("the registry changed under its version");
  });

  it("an unknown schedule says series not found", async () => {
    stub({ dossier: () => err(404, "NOT_FOUND", "no such schedule") });
    mount();
    expect(await screen.findByText("Series not found.")).toBeTruthy();
  });

  it("signed out: no request for the dossier and a sign-in link", async () => {
    const urls = stub({ signedIn: false });
    mount();
    const link = await screen.findByRole("link", { name: "Sign in" });
    expect(link.getAttribute("href")).toBe(`/login?next=${encodeURIComponent(`/p/news/scheduler/s/${SID}/result`)}`);
    expect(urls.some((u) => u.includes("periodic-dossiers"))).toBe(false);
  });

  it("renders in Italian", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    stub(served(resultDossier({ state: "WAITING_FOR_EVIDENCE", profiles: [profile("q1")], human_decisions: [decision("q1")] })));
    mount();
    const banner = await screen.findByRole("region", { name: "Dossier" });
    expect(within(banner).getByTitle("WAITING_FOR_EVIDENCE").textContent).toBe("In attesa di evidenze");
    expect(screen.getByRole("region", { name: "Acquisizione" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Scarica il rapporto in tempo reale (JSON)" })).toBeTruthy();
    expect(screen.getByText("non firmata")).toBeTruthy();
  });
});
