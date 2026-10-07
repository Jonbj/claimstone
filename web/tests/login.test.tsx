// F1: the login page and its redirect. `?next=` is followed only when it is a path that
// starts with a single `/`; the server's message (RATE_LIMITED included) is shown as given.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider, safeNext } from "@/lib/session";
import LoginPage from "@/pages/LoginPage";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

describe("F1: safeNext", () => {
  it.each([
    ["//evil", "/"],
    ["//evil.example/path", "/"],
    ["https://evil.example", "/"],
    ["http://evil.example/x", "/"],
    ["javascript:alert(1)", "/"],
    ["/\\evil", "/"],
    ["evil", "/"],
    ["", "/"],
    [null, "/"],
    ["/p/demo/f/abc?x=1", "/p/demo/f/abc?x=1"],
    ["/admin", "/admin"],
  ])("%s -> %s", (input, expected) => {
    expect(safeNext(input as string | null)).toBe(expected);
  });
});

// A declarative router: the data router builds fetch Requests that jsdom's AbortSignal rejects.
let location = { pathname: "", search: "" };
function Where() {
  location = useLocation();
  return null;
}

function mount(initial: string) {
  render(
    <MemoryRouter initialEntries={[initial]}>
      <Where />
      <Routes>
        <Route path="/login" element={<SessionProvider><LoginPage /></SessionProvider>} />
        <Route path="*" element={<div data-testid="landed" />} />
      </Routes>
    </MemoryRouter>,
  );
  return { state: { get location() { return location; } } };
}

async function fillAndSubmit() {
  await screen.findByLabelText("Operator id");
  fireEvent.change(screen.getByLabelText("Operator id"), { target: { value: "ada" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("F1: the login page", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function server(login: () => Promise<Response>) {
    vi.stubGlobal("fetch", (_url: string, init: RequestInit) =>
      init.method === "POST"
        ? login()
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } }));
  }

  it("returns to ?next= after signing in", async () => {
    server(() => json(200, { operator: { id: "ada", name: "Ada" }, csrf_token: "t" }));
    const router = mount("/login?next=/p/demo/f/abc");
    await fillAndSubmit();
    await waitFor(() => expect(router.state.location.pathname).toBe("/p/demo/f/abc"));
  });

  it("refuses //evil and https://… as a destination", async () => {
    for (const bad of ["//evil.example", "https://evil.example/x"]) {
      cleanup();
      server(() => json(200, { operator: { id: "ada", name: "Ada" }, csrf_token: "t" }));
      const router = mount(`/login?next=${encodeURIComponent(bad)}`);
      await fillAndSubmit();
      await waitFor(() => expect(router.state.location.pathname).toBe("/"));
      expect(router.state.location.search).toBe("");
    }
  });

  it("shows the server's message, RATE_LIMITED as given", async () => {
    const message = "too many failed logins for this id; wait 15 minutes";
    server(() => json(429, { error: { code: "RATE_LIMITED", message } }));
    mount("/login");
    await fillAndSubmit();
    expect(await screen.findByText("RATE_LIMITED")).toBeTruthy();
    expect(screen.getByText(message)).toBeTruthy();
  });

  it("shows a wrong password as the server says it, and stays on the page", async () => {
    server(() => json(401, { error: { code: "UNAUTHORIZED", message: "id or password is wrong" } }));
    const router = mount("/login");
    await fillAndSubmit();
    expect(await screen.findByText("id or password is wrong")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/login");
    expect((screen.getByLabelText("Password") as HTMLInputElement).value).toBe("");
  });
});
