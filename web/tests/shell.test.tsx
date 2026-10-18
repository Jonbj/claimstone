// F1: the shell. Signed out, every page but the door sends the visitor to /login with the page to
// come back to; signed in it shows the operator and Sign out. The rail has no Inbox link, and New project links to the wizard.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Shell from "@/components/Shell";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

let where = "";
function Where() {
  where = useLocation().pathname;
  return null;
}

type Who = "admin" | "operator" | null;

function mount(who: boolean | Who, at = "/p/demo", mustChange = false) {
  const role: Who = who === true ? "admin" : who === false ? null : who;
  vi.stubGlobal("matchMedia", () => ({ matches: false })); // ThemeToggle reads the OS preference
  vi.stubGlobal("fetch", (url: string) => {
    if (url === "/control/v1/session/end") return json(200, { ended: true });
    if (url.startsWith("/control/v1/session")) {
      return role
        ? json(200, { operator: { id: "o1", name: "Ada Lovelace", role, must_change_password: mustChange }, csrf_token: "t" })
        : json(401, { error: { code: "UNAUTHORIZED", message: "no session" } });
    }
    return json(200, { api_version: 1, code: { revision: "abcdef0123456789", dirty: false } });
  });
  render(
    <MemoryRouter initialEntries={[at]}>
      <LocaleProvider>
        <SessionProvider>
          <Where />
          <Routes>
            <Route element={<Shell />}>
              <Route path="/login" element={<div>door</div>} />
              <Route path="*" element={<div>page</div>} />
            </Route>
          </Routes>
        </SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

const linkNames = () => screen.getAllByRole("link").map((a) => a.textContent);

describe("F1: Shell v2", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("sends a signed-out visitor to the door, remembering the page", async () => {
    mount(false);
    await screen.findByText("door");
    expect(where).toBe("/login");
    expect(screen.queryByRole("link", { name: "Today" })).toBeNull();
    expect(screen.queryByText("page")).toBeNull();
  });

  it("shows the operator's name and Sign out when signed in", async () => {
    mount(true);
    expect((await screen.findByTestId("operator-name")).textContent).toBe("Ada Lovelace");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
  });

  it("lists Today and Projects, and no Inbox", async () => {
    mount("operator", "/");
    await screen.findByTestId("operator-name");
    const names = linkNames();
    expect(names).toEqual(expect.arrayContaining(["Today", "Projects"]));
    expect(names).not.toContain("Inbox");
    expect(screen.getByRole("link", { name: "Today" }).getAttribute("aria-current")).toBe("page");
  });

  it("links New project to the wizard when signed in", async () => {
    mount(true);
    const signedIn = await screen.findByRole("link", { name: "+ New project" });
    expect(signedIn.getAttribute("href")).toBe("/new");
  });
  it("shows an operator My account and Administration but not People", async () => {
    mount("operator", "/");
    const account = await screen.findByRole("link", { name: "My account" });
    expect(account.getAttribute("href")).toBe("/account");
    const names = linkNames();
    expect(names).not.toContain("People");
    expect(names).toEqual(expect.arrayContaining(["Today", "Projects", "Administration"]));
  });

  it("shows an admin My account, People and Administration", async () => {
    mount("admin", "/");
    const people = await screen.findByRole("link", { name: "People" });
    expect(people.getAttribute("href")).toBe("/people");
    expect(screen.getByRole("link", { name: "My account" }).getAttribute("href")).toBe("/account");
    expect(screen.getByRole("link", { name: "Administration" }).getAttribute("href")).toBe("/admin");
  });

  it("shows no rail at all when signed out: the door stands alone", async () => {
    mount(null, "/");
    await screen.findByText("door");
    expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
  });

  it("sends a person with a temporary password to /account, and leaves /account alone", async () => {
    mount("operator", "/projects", true);
    await waitFor(() => expect(where).toBe("/account"));
    cleanup();
    mount("operator", "/account", true);
    await screen.findByTestId("operator-name");
    expect(where).toBe("/account");
  });

  it("does not redirect when no change is required", async () => {
    mount("operator", "/projects", false);
    await screen.findByTestId("operator-name");
    // A negative check that gives a late redirect time to happen: waiting for it must time out.
    await expect(waitFor(() => expect(where).not.toBe("/projects"), { timeout: 200 })).rejects.toThrow();
    expect(where).toBe("/projects");
  });

  it("lets a person with a temporary password sign out on /account without a redirect or a trap", async () => {
    mount("operator", "/account", true);
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("door")).toBeTruthy();
    expect(where).toBe("/login");
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
  });

  it("takes Sign in, Sign out, My account and People from the Italian catalog", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    mount("admin", "/");
    expect(await screen.findByRole("link", { name: "Il mio account" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Persone" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Esci" })).toBeTruthy();
  });
});
