// "New series": a series of dated updates from a cadence. The figures are a live preview; the body is
// exactly what the server accepts; a refusal is shown as given and every field is kept; nothing here
// authorizes anything.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import NewSeriesPage from "@/pages/NewSeriesPage";
import { expectNoPurchaseWording } from "./support/purchase";
import { err, json, overviewOf, sent, SID, stub, topic } from "./support/schedulerFixtures";
import type { Routes as StubRoutes } from "./support/schedulerFixtures";

function Where() {
  const { schedule } = useParams();
  return <p>series page {schedule}</p>;
}

function mount() {
  render(
    <MemoryRouter initialEntries={["/p/news/scheduler/new"]}>
      <LocaleProvider>
        <SessionProvider>
          <Routes>
            <Route path="/p/:project/scheduler/new" element={<NewSeriesPage />} />
            <Route path="/p/:project/scheduler/s/:schedule" element={<Where />} />
          </Routes>
        </SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

const FLOWS = [
  { flow_id: "flow-manifest", selector: { round: null, manifest_only: true }, title: "Manifest only" },
  { flow_id: "flow-main", selector: { round: null, manifest_only: false }, title: "Main research" },
];
const PLAN_OK = { rounds: [], schedule_id: SID, schedule_state: "PLANNED", max_total_requests: 72 };
const posted = () => sent.filter((c) => c.method === "POST" && c.url.endsWith("/periodic-plans"));
const tick = (name: RegExp | string) => fireEvent.click(screen.getByRole("checkbox", { name }));

async function ready(routes: StubRoutes = {}) {
  stub({ flows: FLOWS, post: () => json(201, PLAN_OK), ...routes });
  mount();
  await screen.findByRole("combobox", { name: "Flow to repeat" });
  // the figures need the topics: wait until they are read
  await screen.findByText(/Tick at least one source/);
}

describe("New series", () => {
  beforeEach(() => {
    setCsrfToken(null);
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-12T10:00:00Z"));
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear(); });

  it("offers the repeatable flows (manifest-only excluded) and starts at the first of next month, monthly, 3 rounds, no source", async () => {
    await ready();
    const select = screen.getByRole("combobox", { name: "Flow to repeat" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Main research — whole store"]);
    expect((screen.getByLabelText("First start (UTC)") as HTMLInputElement).value).toBe("2026-11-01");
    expect((screen.getByRole("combobox", { name: "Cadence" }) as HTMLSelectElement).value).toBe("monthly");
    expect((screen.getByLabelText(/Number of rounds/) as HTMLInputElement).value).toBe("3");
    expect(screen.getAllByRole("group", { name: /^Round \d$/ })).toHaveLength(3);
    for (const name of ["OpenAlex", "Crossref", "arXiv"]) expect((screen.getByRole("checkbox", { name }) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Tick at least one source/)).toBeTruthy();
  });

  it("the figures follow the sources and the caps, with exact numbers", async () => {
    await ready();   // 2 topics, 4 terms in all, 3 rounds, 3 requests each
    const figs = () => screen.getByRole("region", { name: /Figures/ });
    expect(within(figs()).getByText("Searches per round: —")).toBeTruthy();
    expect(within(figs()).getByText("Request ceiling in all: —")).toBeTruthy();
    tick("OpenAlex");
    expect(within(figs()).getByText("Searches per round: 4")).toBeTruthy();
    tick("Crossref");
    expect(within(figs()).getByText("Searches per round: 8")).toBeTruthy();
    expect(within(figs()).getByText("Searches in all: 24")).toBeTruthy();
    expect(within(figs()).getByText("Requests per round, at most: 24")).toBeTruthy();
    expect(within(figs()).getByText("Request ceiling in all: 72")).toBeTruthy();
    fireEvent.click(screen.getByText(/^Advanced options/));
    fireEvent.change(screen.getByLabelText("Requests per search, at most"), { target: { value: "5" } });
    expect(within(figs()).getByText("Request ceiling in all: 120")).toBeTruthy();
    expect(within(figs()).getByText(/the figure that counts/)).toBeTruthy();
  });

  it("counts the terms of every topic of the chosen flow", async () => {
    await ready({ overview: () => json(200, overviewOf([topic("a", ["x", "y"]), topic("b", ["z", "w"]), topic("c", ["v", "u"])])) });
    tick("OpenAlex");
    expect(within(screen.getByRole("region", { name: /Figures/ })).getByText("Searches per round: 6")).toBeTruthy();
    tick("arXiv");
    expect(within(screen.getByRole("region", { name: /Figures/ })).getByText("Searches per round: 12")).toBeTruthy();
  });

  it("while the searches of the flow are not read, the figures are dashes and saving is disabled with the reason", async () => {
    stub({ flows: FLOWS, overview: () => new Promise<Response>(() => undefined) });
    mount();
    await screen.findByRole("combobox", { name: "Flow to repeat" });
    tick("OpenAlex");
    expect(within(screen.getByRole("region", { name: /Figures/ })).getByText("Searches per round: —")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/still being read/)).toBeTruthy();
  });

  it("if the searches cannot be read, it says why and keeps saving disabled", async () => {
    stub({ flows: FLOWS, overview: () => err(404, "NOT_FOUND", "no such flow") });
    mount();
    await screen.findByRole("combobox", { name: "Flow to repeat" });
    tick("OpenAlex");
    expect(await screen.findByText(/no such flow/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(true);
  });

  it("a start in the past is refused early, in words, and linked to its round", async () => {
    await ready();
    tick("OpenAlex");
    fireEvent.change(screen.getByLabelText("First start (UTC)"), { target: { value: "2026-10-01" } });
    const sentence = await screen.findAllByText("The window starts in the past; it must start in the future.");
    expect(sentence.length).toBeGreaterThan(0);
    const group = screen.getByRole("group", { name: "Round 1" });
    expect(group.getAttribute("aria-describedby")).toBe(sentence[0].id);
    expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(true);
  });

  it("refuses early a round name that already has candidates, including an unbound round", async () => {
    await ready({ unboundRounds: ["update-2026-11"] });
    tick("OpenAlex");
    expect(await screen.findByText("A round with this name already exists in the project.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(true);
  });

  it("every input is labelled and the rounds are one fieldset each", async () => {
    await ready();
    const first = screen.getByRole("group", { name: "Round 1" });
    for (const label of ["Name", "Title", "Starts (UTC)", "Ends (UTC)"]) {
      expect(within(first).getByLabelText(label)).toBeTruthy();
    }
    expect((within(first).getByLabelText("Name") as HTMLInputElement).value).toBe("update-2026-11");
    expect(within(first).getByText("1 Nov 2026, 00:00 UTC")).toBeTruthy();
  });

  it("keeps Advanced options closed, with the suggested defaults in one line, and shows them when opened", async () => {
    await ready();
    tick("OpenAlex");
    const summary = screen.getByText(/^Advanced options/);
    expect(summary.closest("details")!.open).toBe(false);
    expect(summary.textContent).toBe("Advanced options — hosts api.openalex.org; 25 results per search; 3 requests per search at most; up to 4 searches per round");
    fireEvent.click(summary);
    expect((screen.getByLabelText(/^Hosts the searches/) as HTMLTextAreaElement).value).toBe("api.openalex.org");
    expect((screen.getByLabelText("Results per search") as HTMLInputElement).value).toBe("25");
    expect((screen.getByLabelText("Requests per search, at most") as HTMLInputElement).value).toBe("3");
    expect((screen.getByLabelText("Searches per round, at most") as HTMLInputElement).value).toBe("4");
  });

  it("will not let searches per round fall below the number of searches", async () => {
    await ready();
    tick("OpenAlex");
    fireEvent.click(screen.getByText(/^Advanced options/));
    fireEvent.change(screen.getByLabelText("Searches per round, at most"), { target: { value: "2" } });
    expect(screen.getByText("Searches per round cannot be lower than 4.", { exact: false })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(true);
  });

  it("posts exactly the seven keys, sorted sources, hosts from the sources, numbers as numbers", async () => {
    await ready();
    tick("Crossref"); tick("OpenAlex");
    fireEvent.click(screen.getByRole("button", { name: "Save the plan" }));
    await waitFor(() => expect(posted()).toHaveLength(1));
    expect(posted()[0].body).toEqual({
      source_flow_id: "flow-main",
      rounds: [
        { round: "update-2026-11", title: "Update 2026-11", not_before: "2026-11-01T00:00:00Z", expires_at: "2026-12-01T00:00:00Z" },
        { round: "update-2026-12", title: "Update 2026-12", not_before: "2026-12-01T00:00:00Z", expires_at: "2027-01-01T00:00:00Z" },
        { round: "update-2027-01", title: "Update 2027-01", not_before: "2027-01-01T00:00:00Z", expires_at: "2027-02-01T00:00:00Z" },
      ],
      apis: ["crossref", "openalex"],
      allowed_hosts: ["api.crossref.org", "api.openalex.org"],
      max_units_each: 8, max_requests_each: 3, per_query: 25,
    });
  });

  it("a host nobody ticked is permitted but noted; hosts typed by hand are split, trimmed and lowercased", async () => {
    await ready();
    tick("OpenAlex");
    fireEvent.click(screen.getByText(/^Advanced options/));
    fireEvent.change(screen.getByLabelText(/^Hosts the searches/), { target: { value: " API.OpenAlex.org \n\nexport.arxiv.org " } });
    expect(screen.getByText("These hosts are permitted but no ticked source uses them: export.arxiv.org. Remove them unless you mean it.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Save the plan" }));
    await waitFor(() => expect(posted()).toHaveLength(1));
    expect((posted()[0].body as { allowed_hosts: string[] }).allowed_hosts).toEqual(["api.openalex.org", "export.arxiv.org"]);
  });

  it("once the hosts were touched, ticking another source does not widen them: the save is blocked and says which host is missing", async () => {
    await ready();
    tick("OpenAlex");
    fireEvent.click(screen.getByText(/^Advanced options/));
    fireEvent.change(screen.getByLabelText(/^Hosts the searches/), { target: { value: "api.openalex.org\n" } });
    tick("Crossref");
    expect((screen.getByLabelText(/^Hosts the searches/) as HTMLTextAreaElement).value).toBe("api.openalex.org\n");
    expect(screen.getByText(/Add the host of Crossref: api\.crossref\.org\./)).toBeTruthy();
    const save = screen.getByRole("button", { name: "Save the plan" });
    expect(save.hasAttribute("disabled")).toBe(true);
    fireEvent.click(save);
    expect(posted()).toHaveLength(0);
    fireEvent.change(screen.getByLabelText(/^Hosts the searches/), { target: { value: "api.openalex.org\napi.crossref.org" } });
    expect(save.hasAttribute("disabled")).toBe(false);
  });

  it("untouched hosts follow the sources as before", async () => {
    await ready();
    tick("OpenAlex"); tick("arXiv");
    fireEvent.click(screen.getByText(/^Advanced options/));
    expect((screen.getByLabelText(/^Hosts the searches/) as HTMLTextAreaElement).value).toBe("api.openalex.org\nexport.arxiv.org");
  });

  it("a round name equal to a bound flow's gets a note and the server decides; an unbound round blocks", async () => {
    stub({ flows: [...FLOWS, { flow_id: "child", selector: { round: "update-2026-11", manifest_only: false }, title: "Child" }], post: () => json(201, PLAN_OK) });
    mount();
    await screen.findByRole("combobox", { name: "Flow to repeat" });
    await screen.findByText(/Tick at least one source/);
    tick("OpenAlex");
    expect(await screen.findByText("A flow named update-2026-11 already exists. Saving again works only as an exact retry of the same plan; otherwise the server will refuse.")).toBeTruthy();
    expect(screen.queryByText("A round with this name already exists in the project.")).toBeNull();
    expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(false);
  });

  it("times that are not UTC ISO are flagged: date only, no zone, another offset", async () => {
    await ready();
    tick("OpenAlex");
    const first = () => screen.getByRole("group", { name: "Round 1" });
    for (const bad of ["2026-11-01", "2026-11-01T00:00:00", "2026-11-01T00:00:00+01:00"]) {
      fireEvent.change(within(first()).getByLabelText("Starts (UTC)"), { target: { value: bad } });
      expect(within(first()).getByText("Write each time in UTC, like 2026-11-01T00:00:00Z.")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Save the plan" }).hasAttribute("disabled")).toBe(true);
    }
    fireEvent.change(within(first()).getByLabelText("Starts (UTC)"), { target: { value: "2026-11-01T00:00:00+00:00" } });
    expect(within(first()).queryByText("Write each time in UTC, like 2026-11-01T00:00:00Z.")).toBeNull();
  });

  it("explains which flow to pick", async () => {
    await ready();
    expect(screen.getByText("Pick the flow the new rounds continue from.")).toBeTruthy();
  });

  it("after editing a row, changing the count asks inline before regenerating; declining keeps the edit", async () => {
    await ready();
    const name = () => within(screen.getByRole("group", { name: "Round 1" })).getByLabelText("Title") as HTMLInputElement;
    fireEvent.change(name(), { target: { value: "My own title" } });
    fireEvent.change(screen.getByLabelText(/Number of rounds/), { target: { value: "4" } });
    expect(screen.getByText("Regenerate and lose your edits?")).toBeTruthy();
    expect(screen.getAllByRole("group", { name: /^Round \d$/ })).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Keep my edits" }));
    expect(screen.queryByText("Regenerate and lose your edits?")).toBeNull();
    expect(name().value).toBe("My own title");
    expect((screen.getByLabelText(/Number of rounds/) as HTMLInputElement).value).toBe("3");
    fireEvent.change(screen.getByLabelText(/Number of rounds/), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(screen.getAllByRole("group", { name: /^Round \d$/ })).toHaveLength(4);
    expect(name().value).toBe("Update 2026-11");
  });

  it("without edits the rounds regenerate at once, with no question", async () => {
    await ready();
    fireEvent.change(screen.getByLabelText(/Number of rounds/), { target: { value: "5" } });
    expect(screen.queryByText("Regenerate and lose your edits?")).toBeNull();
    expect(screen.getAllByRole("group", { name: /^Round \d$/ })).toHaveLength(5);
  });

  it("success goes to the series page and nothing here says anything is authorized", async () => {
    await ready();
    tick("OpenAlex");
    expect(screen.getByText("It authorizes nothing", { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save the plan" }));
    expect(await screen.findByText(`series page ${SID}`)).toBeTruthy();
  });

  it("a server refusal is shown as given above the button, every field kept, and a second click while busy sends nothing", async () => {
    let release: (r: Response) => void = () => undefined;
    let first = true;
    await ready({ post: () => {
      if (first) { first = false; return new Promise<Response>((resolve) => { release = resolve; }); }
      return json(201, PLAN_OK);
    } });
    tick("OpenAlex");
    fireEvent.change(screen.getByLabelText("First start (UTC)"), { target: { value: "2026-12-01" } });
    const button = screen.getByRole("button", { name: "Save the plan" });
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(screen.getByRole("button", { name: "Saving…" }));
    expect(posted()).toHaveLength(1);
    await act(async () => { release(new Response(JSON.stringify({ error: { code: "REFUSED", message: "round cap must cover every frozen discovery query" } }), { status: 409, headers: { "Content-Type": "application/json" } })); });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("round cap must cover every frozen discovery query");
    expect(alert.compareDocumentPosition(screen.getByRole("button", { name: "Save the plan" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect((screen.getByLabelText("First start (UTC)") as HTMLInputElement).value).toBe("2026-12-01");
    expect((screen.getByRole("checkbox", { name: "OpenAlex" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByText(/series page/)).toBeNull();
  });

  it("warns before the tab is closed once something was typed, and not before", async () => {
    await ready();
    const event = () => { const e = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; };
    expect(event()).toBe(false);
    tick("OpenAlex");
    expect(event()).toBe(true);
  });

  it("signed out: a sign-in line and no request for the project", async () => {
    const urls = stub({ signedIn: false });
    mount();
    expect((await screen.findByRole("link", { name: "Sign in" })).getAttribute("href")).toBe("/login?next=%2Fp%2Fnews%2Fscheduler%2Fnew");
    expect(urls.some((u) => u.startsWith("/api/v1/projects"))).toBe(false);
  });

  it("explains what saving does, and offers no purchase", async () => {
    await ready();
    const block = screen.getByRole("region", { name: "What Claimstone will do after you save" });
    for (const line of ["It freezes one flow and one exact set of searches for each round.", "It writes only a plan to disk.", "It makes no request."]) {
      expect(within(block).getByText(line)).toBeTruthy();
    }
    expect(within(block).getByText(/approve the calendar, separately/)).toBeTruthy();
    expectNoPurchaseWording(document.body.textContent!, "en");
  });

  it("renders in Italian", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    stub({ flows: FLOWS, post: () => json(201, PLAN_OK) });
    mount();
    expect(await screen.findByRole("combobox", { name: "Flusso da ripetere" })).toBeTruthy();
    expect(screen.getByLabelText("Primo avvio (UTC)")).toBeTruthy();
    expect(screen.getByRole("group", { name: "Round 1" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Cosa farà Claimstone dopo il salvataggio" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Salva il piano" })).toBeTruthy();
    expect(await screen.findByText(/Scegli almeno una fonte/)).toBeTruthy();
    expectNoPurchaseWording(document.body.textContent!, "it");
  });
});
