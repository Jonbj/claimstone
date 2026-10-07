// F1: the shell. Signed out it offers Sign in (with the page to come back to); signed in it
// shows the operator and Sign out. The rail has no Inbox link, and New project is disabled
// with its reason.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Shell from "@/components/Shell";
import { setCsrfToken } from "@/lib/control";
import { SessionProvider } from "@/lib/session";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

function mount(signedIn: boolean, at = "/p/demo") {
  vi.stubGlobal("matchMedia", () => ({ matches: false })); // ThemeToggle reads the OS preference
  vi.stubGlobal("fetch", (url: string) => {
    if (url.startsWith("/control/v1/session")) {
      return signedIn
        ? json(200, { operator: { id: "o1", name: "Ada Lovelace" }, csrf_token: "t" })
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } });
    }
    return json(200, { api_version: 1, code: { revision: "abcdef0123456789", dirty: false } });
  });
  render(
    <MemoryRouter initialEntries={[at]}>
      <SessionProvider>
        <Routes>
          <Route element={<Shell />}>
            <Route path="*" element={<div>page</div>} />
          </Route>
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("F1: Shell v2", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows Sign in when signed out, returning to the current page", async () => {
    mount(false);
    const link = await screen.findByRole("link", { name: "Sign in" });
    expect(link.getAttribute("href")).toBe("/login?next=%2Fp%2Fdemo");
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
  });

  it("shows the operator's name and Sign out when signed in", async () => {
    mount(true);
    expect((await screen.findByTestId("operator-name")).textContent).toBe("Ada Lovelace");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
  });

  it("lists Today, Projects and Administration, and no Inbox", async () => {
    mount(false, "/");
    await screen.findByRole("link", { name: "Sign in" });
    const names = screen.getAllByRole("link").map((a) => a.textContent);
    expect(names).toEqual(expect.arrayContaining(["Today", "Projects", "Administration"]));
    expect(names).not.toContain("Inbox");
    expect(screen.getByRole("link", { name: "Today" }).getAttribute("aria-current")).toBe("page");
  });

  it("disables New project and says why", async () => {
    mount(false);
    const button = screen.getByRole("button", { name: "+ New project" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("creating projects from the web is not built yet")).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/rev abcdef012345/)).toBeTruthy());
  });
});
