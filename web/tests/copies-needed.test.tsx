// D140: the page lists the documents Claimstone could not read, with what a person needs to decide to
// get one, and aims the upload at that exact candidate.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CopiesNeeded from "@/components/material/CopiesNeeded";
import { LocaleProvider } from "@/lib/i18n";

const entry = (over: Record<string, unknown>) => ({
  candidate_key: "doi:10.1/a", source_id: null, source_class: "PEER_REVIEWED", state: "not_obtained",
  tooltip: "x", title: "Exercise for depression", year: 2013, venue: "J Sports Med", doi: "10.1/a",
  failure_display: "HTTP 403 (access refused) [PAYWALL_403]", status: null, web_leads: [], ...over,
});

function mount(entries: unknown[], intake: unknown[] = [], onChoose = vi.fn()) {
  render(
    <LocaleProvider>
      <CopiesNeeded entries={entries as never} intake={intake as never} onChoose={onChoose} />
    </LocaleProvider>,
  );
  return onChoose;
}

describe("D140: copies still needed", () => {
  afterEach(() => { cleanup(); localStorage.clear(); });

  it("lists only documents that are not read, with title, venue, cause and the publisher's own page", () => {
    mount([
      entry({}),
      entry({ candidate_key: "doi:10.1/b", state: "confirmed", title: "Already read" }),
      entry({ candidate_key: "doi:10.1/c", state: "not_attempted", title: "Not tried", failure_display: null, doi: null }),
    ]);
    expect(screen.getByText("Exercise for depression")).toBeTruthy();
    expect(screen.queryByText("Already read")).toBeNull();
    expect(screen.getByText(/Behind a paywall/)).toBeTruthy();
    expect(screen.getAllByText(/J Sports Med · 2013/).length).toBeGreaterThan(0);
    const link = screen.getByRole("link", { name: /Publisher page/ });
    expect(link.getAttribute("href")).toBe("https://doi.org/10.1/a");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(screen.getByText("Not tried")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /Publisher page/ })).toHaveLength(1); // no DOI, no link
  });

  it("aims the upload at the chosen candidate", () => {
    const onChoose = mount([entry({})]);
    fireEvent.click(screen.getByRole("button", { name: "Upload the PDF" }));
    expect(onChoose).toHaveBeenCalledWith("doi:10.1/a");
  });

  it("shows a copy the person already offered, and says nothing is bought for them", () => {
    mount([entry({})], [{ kind: "file", state: "QUARANTINED", links: { candidate_key: "doi:10.1/a" } }]);
    expect(screen.getByText(/Your copy:/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upload another" })).toBeTruthy();
    expect(screen.getByText(/buys nothing/)).toBeTruthy();
  });

  it("shows open-web leads as addresses to open, with the project's word on the host and a caveat", () => {
    mount([entry({ web_leads: [
      { url: "https://cs.example.edu/a.pdf", host: "cs.example.edu", title: "x", decision: "ALLOWED" },
      { url: "https://mysite.example/a.pdf", host: "mysite.example", title: null, decision: "UNCLASSIFIED" }] })]);
    const first = screen.getByRole("link", { name: /cs\.example\.edu/ });
    expect(first.getAttribute("href")).toBe("https://cs.example.edu/a.pdf");
    expect(first.getAttribute("rel")).toContain("noopener");
    expect(screen.getByText(/host allowed by the project's policy/)).toBeTruthy();
    expect(screen.getByText(/host not classified by the project — open it yourself/)).toBeTruthy();
    expect(screen.getByText(/nobody has checked that they are this work/)).toBeTruthy();
  });

  it("says so when nothing needs a copy", () => {
    mount([entry({ state: "confirmed" })]);
    expect(screen.getByText(/Every document found has been read/)).toBeTruthy();
  });
});
