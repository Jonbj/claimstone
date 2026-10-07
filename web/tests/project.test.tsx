// F2: the project page. A failed block is named and does not blank the others; flows come
// before legacy rounds, and legacy rounds say "protocol not verified".
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProjectPage from "@/pages/ProjectPage";

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...real,
    api: {
      ...real.api,
      integrity: vi.fn(async () => {
        throw new real.ApiError("LEDGER_CORRUPT", "claims.jsonl: line 3");
      }),
      projects: vi.fn(async () => ({
        api_version: 1,
        projects: [{
          name: "demo", config: "OK", config_error: null, registry_version: 2,
          registry_sha256: "abc", registry_drift: null, integrity_error: null,
          flows: [{ flow_id: "flowaaaaaaaaaaaa", selector_label: "round 1", binding_state: "BOUND",
                    bound_after_data: false, title: "Initial research" }],
          unbound_selectors: [{ slug: "r0", label: "old round", selector: { round: "r0", manifest_only: false } }],
        }],
      })),
      activity: vi.fn(async () => ({ api_version: 1, activity: [] })),
      poll: vi.fn(async () => ({ signature: "s" })),
    },
  };
});

describe("F2: project page", () => {
  afterEach(cleanup);
  it("names the integrity failure and still lists research, flows first", async () => {
    render(
      <MemoryRouter initialEntries={["/p/demo"]}>
        <Routes><Route path="/p/:project" element={<ProjectPage />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("LEDGER_CORRUPT")).toBeTruthy();
    const links = await screen.findAllByRole("link", { name: /Initial research|old round/ });
    expect(links.map((l) => l.textContent)).toEqual([
      expect.stringContaining("Initial research"), expect.stringContaining("old round"),
    ]);
    expect(screen.getByText("protocol not verified")).toBeTruthy();
    expect(screen.getByText("no rows yet")).toBeTruthy();
  });
});
