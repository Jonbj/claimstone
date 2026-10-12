// People (admins): the table, the per-row inline forms that ask for the acting admin's password,
// the add form, and what a non-admin sees (and does not request).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider, STORAGE_KEY } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import PeoplePage from "@/pages/PeoplePage";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

const PEOPLE = [
  { id: "ada", name: "Ada Lovelace", role: "admin", email: "ada@example.org", enabled: true, google_linked: false },
  { id: "bob", name: "Bob Byte", role: "operator", email: null, enabled: true, google_linked: false },
  { id: "cy", name: "Cy Off", role: "operator", email: null, enabled: false, google_linked: false },
];

interface Call { method: string; url: string; body: unknown }
let calls: Call[];

function server(role: "admin" | "operator", act?: (url: string) => Promise<Response>) {
  calls = [];
  vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(String(init.body)) : undefined });
    if (url.startsWith("/control/v1/session")) {
      return json(200, { operator: { id: "ada", name: "Ada Lovelace", role, must_change_password: false }, csrf_token: "t" });
    }
    if (url === "/control/v1/people" && method === "GET") return json(200, { people: PEOPLE });
    if (url.startsWith("/control/v1/people")) {
      return act ? act(url) : json(200, { person: PEOPLE[1] });
    }
    return json(404, { error: { code: "NOT_FOUND", message: "no" } });
  });
}

function mount() {
  render(
    <MemoryRouter>
      <LocaleProvider>
        <SessionProvider><PeoplePage /></SessionProvider>
      </LocaleProvider>
    </MemoryRouter>,
  );
}

const posts = () => calls.filter((c) => c.method === "POST");
const gets = () => calls.filter((c) => c.method === "GET" && c.url === "/control/v1/people");
const row = (name: string) => screen.getByRole("row", { name });

describe("People", () => {
  beforeEach(() => setCsrfToken(null));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("shows an admin the people and their actions", async () => {
    server("admin");
    mount();
    expect(await screen.findByText("Bob Byte")).toBeTruthy();
    expect(within(row("Cy Off")).getByText("disabled")).toBeTruthy();
    expect(within(row("Bob Byte")).getByText("active")).toBeTruthy();
    expect(within(row("Ada Lovelace")).getByText("ada@example.org")).toBeTruthy();
    const bob = within(row("Bob Byte"));
    for (const name of ["Disable", "Set temporary password", "Change email", "Make admin"]) {
      expect(bob.getByRole("button", { name: `${name}: Bob Byte` })).toBeTruthy();
    }
    expect(within(row("Cy Off")).getByRole("button", { name: "Enable: Cy Off" })).toBeTruthy();
    expect(within(row("Ada Lovelace")).getByRole("button", { name: "Make operator: Ada Lovelace" })).toBeTruthy();
  });

  it("tells a non-admin and never calls /people", async () => {
    server("operator");
    mount();
    expect(await screen.findByText("This page is for admins.")).toBeTruthy();
    expect(calls.some((c) => c.url.startsWith("/control/v1/people"))).toBe(false);
  });

  it("hides Disable on the signed-in person's own row", async () => {
    server("admin");
    mount();
    await screen.findByText("Bob Byte");
    expect(within(row("Ada Lovelace")).queryByRole("button", { name: /^Disable/ })).toBeNull();
  });

  it("Disable posts {password} to /people/<id>/disable and reloads", async () => {
    server("admin");
    mount();
    await screen.findByText("Bob Byte");
    const before = gets().length;
    fireEvent.click(screen.getByRole("button", { name: "Disable: Bob Byte" }));
    const form = within(screen.getByRole("form", { name: "Disable: Bob Byte" }));
    fireEvent.change(form.getByLabelText("Your password"), { target: { value: "mine" } });
    fireEvent.click(form.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0]).toMatchObject({ url: "/control/v1/people/bob/disable", body: { password: "mine" } });
    await waitFor(() => expect(gets().length).toBeGreaterThan(before));
    expect(screen.queryByRole("form", { name: "Disable: Bob Byte" })).toBeNull();
  });

  it("sends the new value with the right key for password, email and role", async () => {
    server("admin");
    mount();
    await screen.findByText("Bob Byte");
    const submit = (action: string, fields: Record<string, string>) => {
      fireEvent.click(screen.getByRole("button", { name: `${action}: Bob Byte` }));
      const form = within(screen.getByRole("form", { name: `${action}: Bob Byte` }));
      for (const [label, v] of Object.entries(fields)) fireEvent.change(form.getByLabelText(label), { target: { value: v } });
      fireEvent.click(form.getByRole("button", { name: "Confirm" }));
      return waitFor(() => expect(screen.queryByRole("form", { name: `${action}: Bob Byte` })).toBeNull());
    };
    await submit("Set temporary password", { "Temporary password": "tmp-pass", "Your password": "mine" });
    await submit("Change email", { "New email (leave empty to remove it)": "bob@example.org", "Your password": "mine" });
    await submit("Make admin", { "Your password": "mine" });
    expect(posts().map((c) => [c.url, c.body])).toEqual([
      ["/control/v1/people/bob/password", { password: "mine", new_password: "tmp-pass" }],
      ["/control/v1/people/bob/email", { password: "mine", email: "bob@example.org" }],
      ["/control/v1/people/bob/role", { password: "mine", role: "admin" }],
    ]);
  });

  it("REAUTH says so and clears the password field", async () => {
    server("admin", () => json(403, { error: { code: "REAUTH", message: "password did not match" } }));
    mount();
    await screen.findByText("Bob Byte");
    fireEvent.click(screen.getByRole("button", { name: "Disable: Bob Byte" }));
    const form = within(screen.getByRole("form", { name: "Disable: Bob Byte" }));
    fireEvent.change(form.getByLabelText("Your password"), { target: { value: "wrong" } });
    fireEvent.click(form.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Your password did not match.")).toBeTruthy();
    expect((form.getByLabelText("Your password") as HTMLInputElement).value).toBe("");
  });

  it("shows the last-admin sentence verbatim", async () => {
    const sentence = "the last active admin cannot be disabled or demoted";
    server("admin", () => json(422, { error: { code: "VALIDATION", message: sentence } }));
    mount();
    await screen.findByText("Bob Byte");
    fireEvent.click(screen.getByRole("button", { name: "Make operator: Ada Lovelace" }));
    const form = within(screen.getByRole("form", { name: "Make operator: Ada Lovelace" }));
    fireEvent.change(form.getByLabelText("Your password"), { target: { value: "mine" } });
    fireEvent.click(form.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(sentence)).toBeTruthy();
  });

  it("adds a person with exactly the body the server expects, clears the passwords and says what to do", async () => {
    server("admin");
    mount();
    await screen.findByText("Bob Byte");
    const form = within(screen.getByRole("form", { name: "Add a person" }));
    expect(screen.getByText(/Lowercase letters, digits, dot, dash and underscore; up to 64/)).toBeTruthy();
    fireEvent.change(form.getByLabelText("Id"), { target: { value: "dee" } });
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "Dee Dee" } });
    fireEvent.change(form.getByLabelText("Email (optional)"), { target: { value: "dee@example.org" } });
    fireEvent.change(form.getByLabelText("Role"), { target: { value: "admin" } });
    fireEvent.change(form.getByLabelText("Temporary password"), { target: { value: "tmp-pass" } });
    fireEvent.change(form.getByLabelText("Your password"), { target: { value: "mine" } });
    const before = gets().length;
    fireEvent.click(form.getByRole("button", { name: "Add person" }));
    expect(await screen.findByText("Give them the temporary password in person; they must choose their own at first sign-in.")).toBeTruthy();
    expect(posts()).toHaveLength(1);
    expect(posts()[0].url).toBe("/control/v1/people");
    expect(posts()[0].body).toEqual({
      password: "mine", id: "dee", name: "Dee Dee", email: "dee@example.org", role: "admin", temporary_password: "tmp-pass",
    });
    await waitFor(() => expect(gets().length).toBeGreaterThan(before));
    expect((form.getByLabelText("Your password") as HTMLInputElement).value).toBe("");
    expect((form.getByLabelText("Temporary password") as HTMLInputElement).value).toBe("");
  });

  it("clears the passwords when adding fails, and shows the server's sentence", async () => {
    server("admin", () => json(422, { error: { code: "VALIDATION", message: "that id is taken" } }));
    mount();
    await screen.findByText("Bob Byte");
    const form = within(screen.getByRole("form", { name: "Add a person" }));
    fireEvent.change(form.getByLabelText("Id"), { target: { value: "bob" } });
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "Bob" } });
    fireEvent.change(form.getByLabelText("Temporary password"), { target: { value: "tmp-pass" } });
    fireEvent.change(form.getByLabelText("Your password"), { target: { value: "mine" } });
    fireEvent.click(form.getByRole("button", { name: "Add person" }));
    expect(await screen.findByText("that id is taken")).toBeTruthy();
    expect((form.getByLabelText("Your password") as HTMLInputElement).value).toBe("");
    expect((form.getByLabelText("Temporary password") as HTMLInputElement).value).toBe("");
  });

  it("renders in Italian", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    server("admin");
    mount();
    expect(await screen.findByRole("heading", { name: "Persone" })).toBeTruthy();
    await screen.findByText("Bob Byte");
    expect(screen.getByRole("button", { name: "Disattiva: Bob Byte" })).toBeTruthy();
    expect(screen.getByText(/Lettere minuscole, cifre, punto, trattino e trattino basso; fino a 64/)).toBeTruthy();
    expect(within(row("Cy Off")).getByText("disattivata")).toBeTruthy();
  });

  it("tells a non-admin in Italian", async () => {
    localStorage.setItem(STORAGE_KEY, "it");
    server("operator");
    mount();
    expect(await screen.findByText("Questa pagina è riservata agli amministratori.")).toBeTruthy();
  });
});
