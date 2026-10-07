// F6: Administration. Presence only from the read API; checks and credentials when signed in;
// secret fields cleared after every submit and never echoed; the paid test never called.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider } from "@/lib/session";
import AdminPage from "@/pages/AdminPage";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}
const READ = {
  api_version: 1, credentials: { OLLAMA_API_KEY: true, OPENALEX_API_KEY: false },
  backends: { configured: ["llamacpp"], available: ["llamacpp"] }, backends_note: "note b",
  instruments: { grobid: "0.8" }, key_rotation_note: "rotate by editing .env",
};
const CONTROL = {
  credentials: { OLLAMA_API_KEY: true, OPENALEX_API_KEY: false },
  backends: READ.backends, backends_note: "", instruments: {}, key_rotation_note: "",
  checks: { llamacpp: { kind: "reachability", target: "llamacpp", url: "u", ok: true, status: 200,
                        detail: "", latency_ms: 12, actor: "o1", recorded_at: "2026-10-06T08:12:00Z" } },
  check_targets: { llamacpp: "http://x", "ollama-cloud": "http://y", grobid: "http://z" },
};

const calls: Array<{ url: string; method: string; body?: string }> = [];
function mount(o: { signedIn?: boolean; read?: "fail"; post?: (url: string) => Promise<Response> } = {}) {
  calls.length = 0;
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
    if (url.startsWith("/control/v1/session") && !url.includes("end")) {
      return o.signedIn === false
        ? json(401, { error: { code: "UNAUTHORIZED", message: "no" } })
        : json(200, { operator: { id: "o1", name: "Ada" }, csrf_token: "t" });
    }
    if (url === "/api/v1/admin") {
      return o.read === "fail"
        ? json(500, { error: { code: "INTERNAL", message: "admin unreadable" }, api_version: 1 })
        : json(200, READ);
    }
    if (url === "/control/v1/admin") return json(200, CONTROL);
    if (init?.method === "POST" && o.post) return o.post(url);
    return json(404, { error: { code: "NOT_FOUND", message: "x" } });
  });
  render(
    <MemoryRouter initialEntries={["/admin"]}>
      <SessionProvider>
        <Routes><Route path="/admin" element={<AdminPage />} /></Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("F6: Administration", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("names a failed read", async () => {
    mount({ read: "fail" });
    expect(await screen.findByText("INTERNAL")).toBeTruthy();
    expect(screen.getByText("admin unreadable")).toBeTruthy();
  });

  it("signed out shows presence only and asks for a session for checks", async () => {
    mount({ signedIn: false });
    expect(await screen.findByText(/Sign in to run a reachability check/)).toBeTruthy();
    expect(screen.getByText(/OPENALEX_API_KEY/).parentElement?.textContent).toContain("not set");
    expect(screen.queryByRole("button", { name: /Check/ })).toBeNull();
    expect(calls.filter((c) => c.url === "/control/v1/admin")).toEqual([]);
  });

  it("signed in: last check per target, never-checked said, no check on load", async () => {
    mount();
    expect(await screen.findByText(/reachable · 2026-10-06T08:12:00Z/)).toBeTruthy();
    expect(screen.getAllByText("never checked from here")).toHaveLength(2);
    expect(calls.filter((c) => c.method === "POST")).toEqual([]);
  });

  it("a check button is disabled while any check runs", async () => {
    let release!: (r: Response) => void;
    mount({ post: () => new Promise<Response>((res) => { release = res; }) });
    fireEvent.click(await screen.findByRole("button", { name: "Check grobid" }));
    await waitFor(() => expect((screen.getByRole("button", { name: "Checking…" }) as HTMLButtonElement).disabled).toBe(true));
    expect((screen.getByRole("button", { name: "Check llamacpp" }) as HTMLButtonElement).disabled).toBe(true);
    release(new Response("{}", { status: 201, headers: { "Content-Type": "application/json" } }));
    await screen.findByRole("button", { name: "Check grobid" });
    expect(JSON.parse(calls.find((c) => c.method === "POST")!.body!)).toEqual({ target: "grobid" });
  });

  it("paid test is disabled with the reason and is never called", async () => {
    mount();
    const button = await screen.findByRole("button", { name: "Paid test call" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.title).toMatch(/model-call boundary/);
    fireEvent.click(button);
    expect(calls.some((c) => c.url.includes("paid-test"))).toBe(false);
  });

  async function fillAndSubmit() {
    await screen.findByText("Replace a credential");
    fireEvent.change(screen.getByLabelText("Credential name"), { target: { value: "OLLAMA_API_KEY" } });
    fireEvent.change(screen.getByLabelText("Value"), { target: { value: "s3cret-value" } });
    fireEvent.change(screen.getByLabelText("Your password"), { target: { value: "pw-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Save credential" }));
  }

  it("clears the value and password after success and never renders the value", async () => {
    mount({ post: () => json(201, { credential: { name: "OLLAMA_API_KEY", set: true, note: "restart services" } }) });
    await fillAndSubmit();
    expect(await screen.findByText(/restart services/)).toBeTruthy();
    expect((screen.getByLabelText("Value") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Your password") as HTMLInputElement).value).toBe("");
    expect(document.body.textContent).not.toContain("s3cret-value");
    const sent = JSON.parse(calls.find((c) => c.url.endsWith("/admin/credential"))!.body!);
    expect(sent).toEqual({ name: "OLLAMA_API_KEY", value: "s3cret-value", password: "pw-123" });
  });

  it("clears the fields after a failure and shows CREDENTIALS_READ_ONLY as the server says it", async () => {
    mount({ post: () => json(409, { error: { code: "CREDENTIALS_READ_ONLY", message: "edit .env on the host" } }) });
    await fillAndSubmit();
    expect(await screen.findByText("CREDENTIALS_READ_ONLY")).toBeTruthy();
    expect(screen.getByText("edit .env on the host")).toBeTruthy();
    expect((screen.getByLabelText("Value") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Your password") as HTMLInputElement).value).toBe("");
    expect(document.body.textContent).not.toContain("s3cret-value");
  });
});
