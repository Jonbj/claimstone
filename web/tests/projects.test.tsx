// F2: the projects table filters by name on the client, keeps the server's order, and names a
// failed list.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import IndexPage from "@/pages/IndexPage";

const mk = (name: string) => ({
  name, config: "OK", config_error: null, registry_version: 1, registry_sha256: "h",
  registry_drift: null, integrity_error: null, flows: [],
  unbound_selectors: [{ slug: "-", label: "whole store", selector: { round: null, manifest_only: false } }],
});
const state = { fail: false };

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...real,
    api: {
      ...real.api,
      projects: vi.fn(async () => {
        if (state.fail) throw new real.ApiError("INTERNAL", "boom");
        return { api_version: 1, projects: [mk("zeta"), mk("alpha")] };
      }),
      summary: vi.fn(() => new Promise(() => {})),
    },
  };
});

describe("F2: projects table", () => {
  afterEach(() => {
    cleanup();
    state.fail = false;
  });

  it("filters by name and keeps server order", async () => {
    render(<MemoryRouter><IndexPage /></MemoryRouter>);
    await screen.findByRole("link", { name: "zeta" });
    const names = screen.getAllByRole("rowheader").map((n) => n.textContent ?? "");
    expect(names[0]).toContain("zeta");
    fireEvent.change(screen.getByLabelText("Search projects"), { target: { value: "ALP" } });
    await waitFor(() => expect(screen.queryByRole("link", { name: "zeta" })).toBeNull());
    expect(screen.getByRole("link", { name: "alpha" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Search projects"), { target: { value: "nope" } });
    expect(await screen.findByText(/No project name contains/)).toBeTruthy();
  });

  it("names a failed list", async () => {
    state.fail = true;
    render(<MemoryRouter><IndexPage /></MemoryRouter>);
    expect(await screen.findByText("INTERNAL")).toBeTruthy();
  });
});
