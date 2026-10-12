// My account: who I am, the password change (client-side match only, REAUTH under the field,
// the new value kept), the sessions list and "sign out everywhere else", the forced-change banner.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import AccountPage from "@/pages/AccountPage";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

const ME = { id: "ada", name: "Ada Lovelace", role: "operator", must_change_password: false };
const SESSIONS = [
  { session_id: "s1", created_at: "2026-10-06T20:41:00Z", last_seen: "2026-10-07T08:00:00Z", method: "password", current: true },
  { session_id: "s2", created_at: "2026-10-01T09:00:00Z", last_seen: "2026-10-02T09:30:00Z", method: "password", current: false },
];

interface Call { method: string; url: string; body: unknown }
let calls: Call[];

function server(options: {
  me?: Partial<typeof ME>;
  email?: string | null;
  password?: () => Promise<Response>;
} = {}) {
  calls = [];
  const me = { ...ME, ...options.me };
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(String(init.body)) : undefined });
    if (url.startsWith("/control/v1/session")) return json(200, { operator: me, csrf_token: "t" });
    if (url === "/control/v1/account") {
      return json(200, { operator: { ...me, email: options.email ?? null, google_linked: false } });
    }
    if (url === "/control/v1/account/password") {
      return (options.password ?? (() => json(200, { changed: true })))();
    }
    if (url === "/control/v1/account/sessions") return json(200, { sessions: SESSIONS });
    if (url === "/control/v1/account/sessions/end-others") return json(200, { ended: 1 });
    return json(404, { error: { code: "NOT_FOUND", message: "no" } });
  });
}

function mount() {
  render(
    <MemoryRouter>
      <LocaleProvider>
        <SessionProvider><AccountPage /></SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

const value = (label: string) => (screen.getByLabelText(label) as HTMLInputElement).value;
function type(label: string, text: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value: text } });
}
async function fillPasswords(again = "new-secret") {
  await screen.findByText("Ada Lovelace");
  type("Current password", "old");
  type("New password", "new-secret");
  type("New password again", again);
}
const submitPassword = () => fireEvent.click(screen.getByRole("button", { name: "Change password" }));
const sessionCalls = () => calls.filter((c) => c.url.startsWith("/control/v1/session"));

describe("My account", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("shows name, id, role and email, or 'none'", async () => {
    server({ email: "ada@example.org" });
    mount();
    expect(await screen.findByText("Ada Lovelace")).toBeTruthy();
    expect(screen.getByText("ada")).toBeTruthy();
    expect(screen.getByText("operator")).toBeTruthy();
    expect(screen.getByText("ada@example.org")).toBeTruthy();
    cleanup();
    server();
    mount();
    expect(await screen.findByText("none")).toBeTruthy();
  });

  it("blocks a mismatching 'again' without calling the server", async () => {
    server();
    mount();
    await fillPasswords("other");
    submitPassword();
    expect(await screen.findByText("The two new passwords are not the same.")).toBeTruthy();
    expect(calls.some((c) => c.url.endsWith("/account/password"))).toBe(false);
  });

  it("posts {current,new} once, clears the fields, says so and asks the session again", async () => {
    server();
    mount();
    await fillPasswords();
    const before = sessionCalls().length;
    submitPassword();
    expect(await screen.findByText("Password changed. Your other sessions were signed out.")).toBeTruthy();
    const posts = calls.filter((c) => c.method === "POST" && c.url.endsWith("/account/password"));
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ current: "old", new: "new-secret" });
    expect(value("Current password")).toBe("");
    expect(value("New password")).toBe("");
    expect(value("New password again")).toBe("");
    await waitFor(() => expect(sessionCalls().length).toBeGreaterThan(before));
  });

  it("shows REAUTH under the field and keeps the typed new value", async () => {
    server({ password: () => json(403, { error: { code: "REAUTH", message: "password did not match" } }) });
    mount();
    await fillPasswords();
    submitPassword();
    expect(await screen.findByText("The current password did not match.")).toBeTruthy();
    expect(value("New password")).toBe("new-secret");
    expect(value("New password again")).toBe("new-secret");
    expect(value("Current password")).toBe("");
    expect(screen.queryByText("Password changed. Your other sessions were signed out.")).toBeNull();
  });

  it("shows a 422 and a 429 sentence as the server gave it", async () => {
    for (const [status, code, message] of [
      [422, "VALIDATION", "choose a password of at least 12 characters"],
      [429, "RATE_LIMITED", "too many attempts; wait 15 minutes"],
    ] as const) {
      cleanup();
      server({ password: () => json(status, { error: { code, message } }) });
      mount();
      await fillPasswords();
      submitPassword();
      expect(await screen.findByText(message)).toBeTruthy();
      expect(screen.getByText(code)).toBeTruthy();
    }
  });

  it("lists sessions, marks this one, and 'Sign out everywhere else' posts then reloads", async () => {
    server();
    mount();
    expect(await screen.findByText("this session")).toBeTruthy();
    expect(screen.getAllByText(/^Started /)).toHaveLength(2);
    expect(screen.getByText("Started 6 Oct 2026, 20:41 UTC")).toBeTruthy();
    const listed = () => calls.filter((c) => c.url === "/control/v1/account/sessions").length;
    const before = listed();
    fireEvent.click(screen.getByRole("button", { name: "Sign out everywhere else" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/end-others"))).toBe(true));
    await waitFor(() => expect(listed()).toBeGreaterThan(before));
    expect(await screen.findByText("Signed out 1 other session(s).")).toBeTruthy();
  });

  it("shows the temporary-password banner when a change is required", async () => {
    server({ me: { must_change_password: true } });
    mount();
    expect(await screen.findByText("You are using a temporary password. Choose your own to continue.")).toBeTruthy();
  });

  it("has no banner otherwise", async () => {
    server();
    mount();
    await screen.findByText("Ada Lovelace");
    expect(screen.queryByText(/temporary password/)).toBeNull();
  });

  it("renders in Italian", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    server({ me: { must_change_password: true } });
    mount();
    expect(await screen.findByRole("heading", { name: "Il mio account" })).toBeTruthy();
    expect(screen.getByText("Stai usando una password temporanea. Scegline una tua per continuare.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cambia password" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Esci da tutti gli altri dispositivi" })).toBeTruthy();
    expect(await screen.findByText("questa sessione")).toBeTruthy();
  });
});
