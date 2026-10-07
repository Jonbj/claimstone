// F4.2: the reading desk page decides what the signing area shows. The panel appears only for a
// bound flow, a signed-in person, a question that takes a verdict and a final stored profile;
// every other case says why not, with no form. Stored profiles feed the diff panel.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider } from "@/lib/session";
import QuestionPage from "@/pages/QuestionPage";
import q02 from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/questions/Q02.json";
import profilesFixture from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/questions/Q02.profiles.json";

const FLOW = "0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd";
const HASH = q02.profile_fields.profile_sha256 as string;

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

const finalQuestion = {
  ...q02,
  profile_fields: { ...q02.profile_fields, provisional: false, state: "FINAL", blocking: [] },
};
const operational = {
  ...finalQuestion, kind: "operational", operational_not_applicable: true,
  not_applicable_state: "LITERATURE_VERDICT_NOT_APPLICABLE",
};

let posts: Array<{ url: string; body: Record<string, unknown> }>;

function mount(opts: {
  question?: unknown; signedIn?: boolean; kind?: "f" | "u"; profilesStatus?: number;
  profiles?: unknown;
}) {
  const { question = finalQuestion, signedIn = true, kind = "f", profilesStatus = 200,
    profiles = profilesFixture } = opts;
  posts = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (url.startsWith("/control/v1/session")) {
      return signedIn
        ? json(200, { operator: { id: "o1", name: "Ada" }, csrf_token: "t" })
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } });
    }
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body)) });
      return json(201, { adjudication: {
        verdict: "NEVER_ASKED", adjudicated_by: "Ada", profile_sha256: HASH } });
    }
    if (url.includes("/draft")) {
      return json(200, { draft: null, current: null, current_profile_sha256: HASH });
    }
    if (url.endsWith("/profiles")) {
      return profilesStatus === 200
        ? json(200, profiles)
        : json(profilesStatus, { error: { code: "NOT_FOUND", message: "no profiles here" } });
    }
    if (url.includes("/questions/Q02")) return json(200, question);
    if (url.includes("/poll")) return json(200, { ledgers: {} });
    return json(404, { error: { code: "NOT_FOUND", message: "x" } });
  });
  const path = kind === "f" ? `/p/demo/f/${FLOW}/q/Q02` : "/p/demo/u/-/q/Q02";
  render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <Routes>
          <Route path="/p/:project/f/:sel/q/:qid" element={<QuestionPage kind="f" />} />
          <Route path="/p/:project/u/:sel/q/:qid" element={<QuestionPage kind="u" />} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => setCsrfToken(null));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("F4.2: reading desk", () => {
  it("signed in on a final profile of a bound flow: the panel, with no verdict chosen", async () => {
    mount({});
    expect(await screen.findByRole("form", { name: "Sign the verdict" })).toBeTruthy();
    expect((screen.getAllByRole("radio") as HTMLInputElement[]).every((r) => !r.checked)).toBe(true);
    expect(screen.getByRole("button", { name: "Sign as Ada" })).toBeTruthy();
  });

  it("a provisional profile shows its state and no signature panel", async () => {
    mount({ question: q02 });
    expect(await screen.findByText(/This profile is provisional/)).toBeTruthy();
    expect(screen.queryByRole("form")).toBeNull();
    expect(screen.queryAllByRole("radio").length).toBe(0);
  });

  it("an operational question shows the API's state and no panel", async () => {
    mount({ question: operational });
    expect((await screen.findAllByText("LITERATURE_VERDICT_NOT_APPLICABLE")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("form")).toBeNull();
    expect(screen.queryAllByRole("radio").length).toBe(0);
  });

  it("signed out says to sign in and offers no panel", async () => {
    mount({ signedIn: false });
    expect(await screen.findByText(/Sign in to sign\./)).toBeTruthy();
    expect(screen.queryByRole("form")).toBeNull();
  });

  it("an unbound selector offers no panel", async () => {
    mount({ kind: "u" });
    expect(await screen.findByText(/not bound to a flow/)).toBeTruthy();
    expect(screen.queryByRole("form")).toBeNull();
  });

  it("the stored profiles feed the diff panel; a failed list falls back to pasting", async () => {
    mount({});
    await screen.findByRole("form", { name: "Sign the verdict" });
    await waitFor(() => expect(screen.getAllByRole("combobox").length).toBe(2));
    expect(screen.queryAllByRole("textbox").filter((t) => t.tagName === "INPUT").length).toBe(0);
    cleanup();
    mount({ profilesStatus: 404 });
    await screen.findByRole("form", { name: "Sign the verdict" });
    await waitFor(() => expect(screen.getByText("no profiles here")).toBeTruthy());
    expect(screen.queryAllByRole("combobox").length).toBe(0);
    expect(screen.getAllByRole("textbox").filter((t) => t.tagName === "INPUT").length).toBe(2);
  });

  it("after signing it shows the stored row and stays on the page", async () => {
    mount({});
    await screen.findByRole("form", { name: "Sign the verdict" });
    fireEvent.click(screen.getByRole("radio", { name: /Never asked/ }));
    fireEvent.change(screen.getAllByRole("textbox").find((t) => t.tagName === "TEXTAREA")!,
      { target: { value: "y".repeat(130) } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Sign as Ada" }));
    const done = await screen.findByLabelText("Signed verdict");
    expect(done.textContent).toContain("NEVER_ASKED");
    expect(done.textContent).toContain(HASH);
    expect(posts.find((p) => p.url.endsWith("/adjudicate"))!.body).toEqual({
      verdict: "NEVER_ASKED", rationale: "y".repeat(130), profile_sha256: HASH, attest: true });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Q02");
  });
});
