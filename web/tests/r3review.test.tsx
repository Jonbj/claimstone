// Review of R3: an API error on an index row or an inbox selector shows its code and message
// on screen (never a generic "unavailable"), and inbox groups follow the API's project order,
// not the order the answers happen to arrive.
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

const projects = {
  api_version: 1,
  projects: [
    { name: "alpha", config: "OK", config_error: null, registry_version: 1, registry_sha256: "a",
      registry_drift: null, integrity_error: null, flows: [],
      unbound_selectors: [{ slug: "-", label: "whole store", selector: { round: null, manifest_only: false } }] },
    { name: "beta", config: "OK", config_error: null, registry_version: 1, registry_sha256: "b",
      registry_drift: null, integrity_error: null, flows: [],
      unbound_selectors: [{ slug: "-", label: "whole store", selector: { round: null, manifest_only: false } }] },
  ],
};

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...real,
    api: {
      ...real.api,
      projects: vi.fn(async () => projects),
      meta: vi.fn(async () => ({ api_version: 1, code: { revision: "r", dirty: false } })),
      summary: vi.fn(async () => {
        throw new real.ApiError("LEDGER_CORRUPT", "flows.jsonl: line 1 is not valid JSON");
      }),
      inbox: vi.fn(async (project: string) => {
        // alpha answers last: arrival order must not decide display order
        if (project === "alpha") await new Promise((r) => setTimeout(r, 30));
        return { api_version: 1, cards: [{ category: "ADVISORY", scope: "s", subject: project,
                                           cause: "c", command: null, note: "" }] };
      }),
    },
  };
});

afterEach(() => vi.clearAllMocks());

describe("review of R3", () => {
  it("shows the error code and message on an index row", async () => {
    const { default: IndexPage } = await import("@/pages/IndexPage");
    render(<MemoryRouter><IndexPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText("LEDGER_CORRUPT").length).toBe(2));
    expect(screen.getAllByText("flows.jsonl: line 1 is not valid JSON").length).toBe(2);
    expect(screen.queryByText(/summary unavailable/)).toBeNull();
  });

  it("orders inbox groups by the API's project order", async () => {
    const { default: InboxPage } = await import("@/pages/InboxPage");
    const { container } = render(<MemoryRouter><InboxPage /></MemoryRouter>);
    await waitFor(() => expect(container.textContent).toContain("alpha"));
    await waitFor(() => expect(container.textContent).toContain("beta"));
    const text = container.textContent ?? "";
    expect(text.indexOf("alpha")).toBeLessThan(text.indexOf("beta"));
  });
});
