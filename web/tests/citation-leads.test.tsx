// D143: leads are suggestions with a count of sources; proposing one goes through the intake.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CitationLeads from "@/components/material/CitationLeads";
import { setCsrfToken } from "@/lib/control";
import { LocaleProvider } from "@/lib/i18n";

const lead = { doi: "10.7000/hot", links: 3, seeds: ["a", "b", "c"], directions: ["cites"], title: "A hot paper", year: 2020, venue: "J Hot" };

describe("D143: citation leads", () => {
  beforeEach(() => setCsrfToken("t"));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

  it("renders nothing when there are no leads", () => {
    const { container } = render(<LocaleProvider><CitationLeads project="p" flowId="f" leads={[]} onDone={() => {}} /></LocaleProvider>);
    expect(container.textContent).toBe("");
  });

  it("labels the number as a count of sources and proposes the DOI through the intake", async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
      return Promise.resolve(new Response(JSON.stringify({ intake: { state: "READY" } }), { status: 201, headers: { "Content-Type": "application/json" } }));
    });
    const done = vi.fn();
    render(<LocaleProvider><CitationLeads project="p" flowId="f" leads={[lead]} onDone={done} /></LocaleProvider>);
    expect(screen.getByText("A hot paper")).toBeTruthy();
    expect(screen.getByText(/a count of sources, not a measure of relevance/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Propose" }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(calls[0].url).toContain("/intake");
    expect(calls[0].body).toMatchObject({ kind: "doi", value: "10.7000/hot" });
    expect(screen.getByText(/Proposed:/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Propose" })).toBeNull();
  });
});
