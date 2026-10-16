import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProjectPage from "@/pages/ProjectPage";
import { api } from "@/lib/api";
import { ControlError, control } from "@/lib/control";
import { SessionProvider } from "@/lib/session";

const operator = { id: "o", name: "Operator", role: "admin" as const, must_change_password: false };
let signedIn = true;

function mount() {
  render(<MemoryRouter initialEntries={["/p/demo"]}><SessionProvider><Routes>
    <Route path="/p/:project" element={<ProjectPage />} />
    <Route path="/p/:project/f/:sel" element={<p>flow page</p>} />
  </Routes></SessionProvider></MemoryRouter>);
}

describe("first search empty state", () => {
  beforeEach(() => {
    signedIn = true;
    vi.spyOn(api, "projects").mockResolvedValue({ api_version: 1, projects: [{
      name: "demo", config: "OK", config_error: null, registry_version: 1,
      registry_sha256: "abc", registry_drift: null, integrity_error: null,
      flows: [], unbound_selectors: [],
    }] } as Awaited<ReturnType<typeof api.projects>>);
    vi.spyOn(api, "integrity").mockRejectedValue(new Error("unavailable"));
    vi.spyOn(api, "activity").mockResolvedValue({ api_version: 1, project: "demo", activity: [] });
    vi.spyOn(api, "poll").mockRejectedValue(new Error("poll unavailable"));
    vi.spyOn(control, "session").mockImplementation(async () => {
      if (!signedIn) throw new ControlError(401, "UNAUTHORIZED", "sign in");
      return { operator, csrf_token: "tok" };
    });
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("shows UTC default values and validates before posting", async () => {
    const start = vi.spyOn(control, "startFlow");
    mount();
    expect(await screen.findByRole("heading", { name: "Start the first search" })).toBeTruthy();
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("First search");
    expect((screen.getByLabelText("Round name") as HTMLInputElement).value)
      .toBe(`first-${new Date().toISOString().slice(0, 10)}`);
    fireEvent.change(screen.getByLabelText("Round name"), { target: { value: "bad round" } });
    fireEvent.click(screen.getByRole("button", { name: "Create flow" }));
    expect(await screen.findByText(/Round name must start/)).toBeTruthy();
    expect(start).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Round name"), { target: { value: "r" } });
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: " " } });
    fireEvent.click(screen.getByRole("button", { name: "Create flow" }));
    expect(await screen.findByText("Title must be 1 to 120 characters.")).toBeTruthy();
    expect(start).not.toHaveBeenCalled();
  });

  it("navigates after success and shows a server refusal verbatim", async () => {
    const start = vi.spyOn(control, "startFlow")
      .mockRejectedValueOnce(new Error("population changed"))
      .mockResolvedValueOnce({ flow_id: "f1", created: true, title: "First search", round: "r" });
    mount();
    await screen.findByRole("button", { name: "Create flow" });
    fireEvent.click(screen.getByRole("button", { name: "Create flow" }));
    expect(await screen.findByText("population changed")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Round name"), { target: { value: "r" } });
    fireEvent.click(screen.getByRole("button", { name: "Create flow" }));
    await waitFor(() => expect(screen.getByText("flow page")).toBeTruthy());
    expect(start).toHaveBeenCalledTimes(2);
  });

  it("offers sign in when unsigned", async () => {
    signedIn = false;
    mount();
    expect(await screen.findByRole("link", { name: "Sign in to start the first search" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Create flow" })).toBeNull();
  });
});
