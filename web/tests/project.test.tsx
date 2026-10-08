// F2: the project page. A failed block is named and does not blank the others; flows come
// before legacy rounds, and legacy rounds say "protocol not verified".
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProjectPage from "@/pages/ProjectPage";

type Flow = { flow_id: string; selector_label: string; binding_state: string; bound_after_data: boolean; title: string };
const flow = (id: string, state: string, title: string): Flow =>
  ({ flow_id: id, selector_label: "round 1", binding_state: state, bound_after_data: false, title });
let flows: Flow[] = [];

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
          flows,
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
  beforeEach(() => {
    flows = [flow("flowaaaaaaaaaaaa", "REGISTRY_DRIFTED", "Initial research"), flow("flowbbbbbbbbbbbb", "PROTOCOL_DRIFTED", "October update")];
  });
  it("names the integrity failure and still lists research, flows first", async () => {
    render(
      <MemoryRouter initialEntries={["/p/demo"]}>
        <Routes><Route path="/p/:project" element={<ProjectPage />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("LEDGER_CORRUPT")).toBeTruthy();
    const links = await screen.findAllByRole("link", { name: /Initial research|October update|old round/ });
    expect(links.map((l) => l.textContent)).toEqual([
      expect.stringContaining("Initial research"), expect.stringContaining("October update"),
      expect.stringContaining("old round"),
    ]);
    expect(screen.getByText("protocol not verified")).toBeTruthy();
    expect(screen.getByText("no rows yet")).toBeTruthy();
  });

  function mount(path: string) {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/p/:project" element={<ProjectPage />} />
          <Route path="/p/:project/f/:sel" element={<p>the journey of {"flow"}</p>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("keeps the technical details collapsed, with the integrity failure named in the summary", async () => {
    mount("/p/demo");
    await screen.findByText("LEDGER_CORRUPT");
    const details = screen.getByText(/^Technical details/).closest("details")!;
    expect(details.open).toBe(false);
    expect(within(details).getByText("integrity could not be read")).toBeTruthy();
  });

  it("redirects to the only bound flow", async () => {
    flows = [flow("flowaaaaaaaaaaaa", "REGISTRY_DRIFTED", "Initial research")];
    mount("/p/demo");
    expect(await screen.findByText("the journey of flow")).toBeTruthy();
  });

  it("redirects to the one CURRENT flow among several", async () => {
    flows = [flow("flowaaaaaaaaaaaa", "REGISTRY_DRIFTED", "Initial research"), flow("flowbbbbbbbbbbbb", "CURRENT", "October update")];
    mount("/p/demo");
    expect(await screen.findByText("the journey of flow")).toBeTruthy();
  });

  it("lists the flows when two are CURRENT or none is", async () => {
    flows = [flow("flowaaaaaaaaaaaa", "CURRENT", "Initial research"), flow("flowbbbbbbbbbbbb", "CURRENT", "October update")];
    mount("/p/demo");
    expect(await screen.findByRole("link", { name: /October update/ })).toBeTruthy();
    expect(screen.queryByText("the journey of flow")).toBeNull();
  });

  it("?details=1 suppresses the redirect so the technical details stay reachable", async () => {
    flows = [flow("flowaaaaaaaaaaaa", "CURRENT", "Initial research")];
    mount("/p/demo?details=1");
    expect(await screen.findByRole("link", { name: /Initial research/ })).toBeTruthy();
    expect(screen.queryByText("the journey of flow")).toBeNull();
    expect(screen.getByText(/^Technical details/).closest("details")!.open).toBe(true);
  });
});
