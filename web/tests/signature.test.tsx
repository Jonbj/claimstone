// F4: the signature panel. No verdict is preselected or remembered; Sign needs a chosen verdict,
// 120 trimmed characters and the attestation; the POST carries exactly the four fields and the
// hash displayed; a 409 shows the server's code and sentence; STALE_PROFILE keeps the text and
// offers the reload and the diff; the stored row is shown after success.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SignaturePanel from "@/components/SignaturePanel";
import { setCsrfToken } from "@/lib/control";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const TEXT = "x".repeat(120);

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

let posts: Array<{ url: string; body: Record<string, unknown> }>;
let adjudicate: () => Promise<Response>;
let draftReply: unknown = { draft: null, current: null, current_profile_sha256: HASH_A };
let draftGets: number;
let saveReply: () => Promise<Response>;

function stubFetch() {
  posts = [];
  draftGets = 0;
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body)) });
      if (url.endsWith("/adjudicate")) return adjudicate();
      if (url.endsWith("/draft")) return saveReply();
    }
    if (url.endsWith("/draft")) {
      draftGets += 1;
      return json(200, draftReply);
    }
    return json(404, { error: { code: "NOT_FOUND", message: "x" } });
  });
}

const handlers = {
  onReload: vi.fn(), onCompare: vi.fn(), onSigned: vi.fn(),
};

function mount(latestHash = HASH_A, qid = "Q04") {
  return render(
    <SignaturePanel project="demo" flowId="f1" qid={qid} operatorName="Ada" latestHash={latestHash}
      {...handlers} />,
  );
}
const signButton = () => screen.getByRole("button", { name: /^Sign as Ada|^Signing/ }) as HTMLButtonElement;
const area = () => screen.getByRole("textbox") as HTMLTextAreaElement;
const type = (text: string) => fireEvent.change(area(), { target: { value: text } });

function ready() {
  fireEvent.click(screen.getByRole("radio", { name: /Contested in literature/ }));
  type(TEXT);
  fireEvent.click(screen.getByRole("checkbox"));
}

beforeEach(() => {
  setCsrfToken("t");
  adjudicate = () => json(201, { adjudication: {
    verdict: "CONTESTED_IN_LITERATURE", adjudicated_by: "Ada", profile_sha256: HASH_A } });
  draftReply = { draft: null, current: null, current_profile_sha256: HASH_A };
  saveReply = () => json(201, { draft: {}, current: true, current_profile_sha256: HASH_A });
  stubFetch();
  Object.values(handlers).forEach((h) => h.mockReset());
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); setCsrfToken(null); });

describe("F4.3: signature panel", () => {
  it("offers exactly the five verdicts, none checked, never NO_VERIFIED_CLAIM", () => {
    mount();
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.value)).toEqual([
      "SUPPORTED", "CONTRADICTED", "CONTESTED_IN_LITERATURE", "UNANSWERED_IN_LITERATURE", "NEVER_ASKED"]);
    expect(radios.every((r) => !r.checked)).toBe(true);
    expect(document.body.textContent).not.toContain("NO_VERIFIED_CLAIM");
    expect(document.body.textContent).toContain("the literature speaks and disagrees irreducibly");
    expect(document.body.textContent).toContain("none selected");
  });

  it("a choice does not carry to the next question's panel", () => {
    const first = mount(HASH_A, "Q04");
    fireEvent.click(screen.getByRole("radio", { name: /Supported/ }));
    first.unmount();
    mount(HASH_A, "Q05");
    expect((screen.getAllByRole("radio") as HTMLInputElement[]).every((r) => !r.checked)).toBe(true);
  });

  it("counts trimmed characters live and enables Sign only when all three hold", () => {
    mount();
    expect(signButton().disabled).toBe(true);
    type(`   ${"x".repeat(119)}   `);
    expect(screen.getByTestId("char-count").textContent).toContain("119 characters");
    fireEvent.click(screen.getByRole("radio", { name: /Supported/ }));
    fireEvent.click(screen.getByRole("checkbox"));
    expect(signButton().disabled).toBe(true);
    type(`  ${TEXT}  `);
    expect(screen.getByTestId("char-count").textContent).toContain("120 characters");
    expect(signButton().disabled).toBe(false);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(signButton().disabled).toBe(true);
  });

  it("without a verdict Sign stays disabled even with text and attestation", () => {
    mount();
    type(TEXT);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(signButton().disabled).toBe(true);
  });

  it("posts exactly the four fields with the displayed hash, once, disabled while running, then shows the stored row", async () => {
    let release: (r: Response) => void = () => {};
    adjudicate = () => new Promise<Response>((resolve) => { release = resolve; });
    mount();
    ready();
    fireEvent.click(signButton());
    fireEvent.click(signButton());
    await waitFor(() => expect(posts.length).toBe(1));
    expect(posts[0].url).toBe("/control/v1/p/demo/flows/f1/q/Q04/adjudicate");
    expect(posts[0].body).toEqual({
      verdict: "CONTESTED_IN_LITERATURE", rationale: TEXT, profile_sha256: HASH_A, attest: true });
    expect(signButton().disabled).toBe(true);
    release(new Response(JSON.stringify({ adjudication: {
      verdict: "CONTESTED_IN_LITERATURE", adjudicated_by: "Ada", profile_sha256: HASH_A } }), {
      status: 201, headers: { "Content-Type": "application/json" } }));
    const done = await screen.findByLabelText("Signed verdict");
    expect(done.textContent).toContain("CONTESTED_IN_LITERATURE");
    expect(done.textContent).toContain("Ada");
    expect(done.textContent).toContain(HASH_A);
    expect(posts.length).toBe(1);
    expect(handlers.onSigned).toHaveBeenCalledTimes(1);
  });

  it("a 409 shows the server's code and sentence verbatim and keeps the form", async () => {
    adjudicate = () => json(409, { error: { code: "PROVISIONAL", message: "the profile is provisional: a round is open." } });
    mount();
    ready();
    fireEvent.click(signButton());
    const alert = await screen.findByText("the profile is provisional: a round is open.");
    expect(alert.closest("[role=alert]")!.textContent).toContain("PROVISIONAL");
    expect(area().value).toBe(TEXT);
    expect(screen.queryByTestId("evidence-changed")).toBeNull();
  });

  it("STALE_PROFILE: banner, text kept, signing blocked, reload, then diff and adopt when the page knows the new hash", async () => {
    adjudicate = () => json(409, { error: { code: "STALE_PROFILE", message: "the evidence moved since you read it" } });
    const view = mount(HASH_A);
    ready();
    fireEvent.click(signButton());
    await screen.findByText("the evidence moved since you read it");
    expect(screen.getByTestId("evidence-changed").textContent).toContain("The evidence changed");
    expect(handlers.onReload).toHaveBeenCalled();
    expect(area().value).toBe(TEXT);
    expect(signButton().disabled).toBe(true);
    // The page reloads and now holds the new hash.
    view.rerender(<SignaturePanel project="demo" flowId="f1" qid="Q04" operatorName="Ada"
      latestHash={HASH_B} {...handlers} />);
    fireEvent.click(screen.getByRole("button", { name: "Compare with the current profile" }));
    expect(handlers.onCompare).toHaveBeenCalledWith(HASH_A, HASH_B);
    expect(signButton().disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Use the current profile" }));
    expect(screen.queryByTestId("evidence-changed")).toBeNull();
    expect(area().value).toBe(TEXT);
    // The attestation was for the old profile: it must be given again.
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("checkbox"));
    adjudicate = () => json(201, { adjudication: { verdict: "CONTESTED_IN_LITERATURE", adjudicated_by: "Ada", profile_sha256: HASH_B } });
    fireEvent.click(signButton());
    await waitFor(() => expect(posts.length).toBe(2));
    expect(posts[1].body.profile_sha256).toBe(HASH_B);
  });

  it("a hash change under the reader blocks signing without signing anything", () => {
    const view = mount(HASH_A);
    ready();
    view.rerender(<SignaturePanel project="demo" flowId="f1" qid="Q04" operatorName="Ada"
      latestHash={HASH_B} {...handlers} />);
    expect(screen.getByTestId("evidence-changed")).toBeTruthy();
    expect(signButton().disabled).toBe(true);
    expect(posts.length).toBe(0);
  });
});

const draftPosts = () => posts.filter((p) => p.url.endsWith("/draft"));

describe("F4.4: drafts", () => {
  it("reads the draft on load and puts the text back; a current draft blocks nothing", async () => {
    draftReply = { draft: { rationale: TEXT, profile_sha256: HASH_A, verdict: "SUPPORTED" },
      current: true, current_profile_sha256: HASH_A };
    mount();
    await waitFor(() => expect(area().value).toBe(TEXT));
    expect(draftGets).toBe(1);
    expect(screen.queryByTestId("draft-changed")).toBeNull();
    // The draft never restores a verdict or the attestation.
    expect((screen.getAllByRole("radio") as HTMLInputElement[]).every((r) => !r.checked)).toBe(true);
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
  });

  it("a draft from another profile: banner, text back, signing blocked until the profile is reloaded", async () => {
    draftReply = { draft: { rationale: TEXT, profile_sha256: HASH_B },
      current: false, current_profile_sha256: HASH_A };
    mount(HASH_A);
    const bannerEl = await screen.findByTestId("draft-changed");
    expect(bannerEl.textContent).toContain("The profile changed while you read");
    expect(area().value).toBe(TEXT);
    fireEvent.click(screen.getByRole("radio", { name: /Supported/ }));
    fireEvent.click(screen.getByRole("checkbox"));
    expect(signButton().disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Compare with the current profile" }));
    expect(handlers.onCompare).toHaveBeenCalledWith(HASH_B, HASH_A);
    fireEvent.click(screen.getByRole("button", { name: "Reload the profile" }));
    expect(handlers.onReload).toHaveBeenCalled();
    expect(screen.queryByTestId("draft-changed")).toBeNull();
    // The attestation was for the old reading: given again after the reload.
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(signButton().disabled).toBe(false);
    fireEvent.click(signButton());
    await waitFor(() => expect(posts.some((p) => p.url.endsWith("/adjudicate"))).toBe(true));
    expect(posts.find((p) => p.url.endsWith("/adjudicate"))!.body.profile_sha256).toBe(HASH_A);
  });

  it("Save draft posts the text and the shown hash only, never the verdict", async () => {
    mount();
    fireEvent.click(screen.getByRole("radio", { name: /Supported/ }));
    expect((screen.getByRole("button", { name: "Save draft" }) as HTMLButtonElement).disabled).toBe(true);
    type("some reasoning");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(draftPosts().length).toBe(1));
    expect(draftPosts()[0].body).toEqual({ rationale: "some reasoning", profile_sha256: HASH_A });
    expect(await screen.findByText("Draft saved")).toBeTruthy();
  });

  it("saves on blur only when the text changed since the last save, and never on a keystroke", async () => {
    mount();
    type("first");
    type("first and more");
    await new Promise((r) => setTimeout(r, 30));
    expect(draftPosts().length).toBe(0);
    fireEvent.blur(area());
    await waitFor(() => expect(draftPosts().length).toBe(1));
    await screen.findByText("Draft saved");
    fireEvent.blur(area());
    await new Promise((r) => setTimeout(r, 30));
    expect(draftPosts().length).toBe(1);
    type("first and more again");
    fireEvent.blur(area());
    await waitFor(() => expect(draftPosts().length).toBe(2));
  });

  it("a loaded draft is not re-saved on blur until it is edited", async () => {
    draftReply = { draft: { rationale: "kept", profile_sha256: HASH_A },
      current: true, current_profile_sha256: HASH_A };
    mount();
    await waitFor(() => expect(area().value).toBe("kept"));
    fireEvent.blur(area());
    await new Promise((r) => setTimeout(r, 30));
    expect(draftPosts().length).toBe(0);
  });

  it("a failed save is named and the text stays", async () => {
    saveReply = () => json(422, { error: { code: "VALIDATION", message: "draft too long" } });
    mount();
    type("abc");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("draft too long")).toBeTruthy();
    expect(area().value).toBe("abc");
  });
});
