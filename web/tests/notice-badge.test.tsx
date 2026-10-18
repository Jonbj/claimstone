// D142: a Crossref notice is shown; silence is not a green mark; a failed lookup is its own word.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import NoticeBadge from "@/components/NoticeBadge";
import SourceTracker from "@/components/SourceTracker";
import { LocaleProvider } from "@/lib/i18n";

const status = (over: Record<string, unknown>) => ({
  state: "NOTICE_RECORDED", withdrawing: true, observed_at: "2026-10-18", notices: [], ...over,
});

const wrap = (node: React.ReactNode) => render(<LocaleProvider>{node}</LocaleProvider>);

describe("D142: notices", () => {
  afterEach(() => { cleanup(); localStorage.clear(); });

  it("names a retraction as withdrawing and a correction as a correction", () => {
    wrap(<NoticeBadge status={status({ notices: [
      { type: "retraction", kind: "withdrawing", label: "Retraction" },
      { type: "correction", kind: "correcting", label: null }] }) as never} />);
    expect(screen.getByText(/Retraction or concern notice · Retraction/)).toBeTruthy();
    expect(screen.getByText(/Correction notice/)).toBeTruthy();
  });

  it("never turns silence into a clean mark", () => {
    wrap(<NoticeBadge status={status({ state: "NO_NOTICE_RECORDED", withdrawing: false }) as never} />);
    expect(screen.getByText(/not proof there is none/)).toBeTruthy();
    expect(screen.queryByText(/clean|ok|not retracted/i)).toBeNull();
  });

  it("says a failed lookup failed, and renders nothing for a source nobody asked about", () => {
    wrap(<NoticeBadge status={status({ state: "LOOKUP_FAILED", withdrawing: false }) as never} />);
    expect(screen.getByText(/Notice lookup failed/)).toBeTruthy();
    cleanup();
    const { container } = wrap(<NoticeBadge status={null} />);
    expect(container.textContent).toBe("");
  });

  it("lists the sources that carry a notice under the tracker, with a warning to read it", () => {
    const entry = (key: string, st: unknown) => ({
      candidate_key: key, source_id: null, source_class: "ACA", state: "confirmed", tooltip: "t", title: `T ${key}`,
      year: 2020, venue: "V", doi: null, failure_display: null, status: st });
    wrap(<SourceTracker entries={[
      entry("a", status({ notices: [{ type: "retraction", kind: "withdrawing", label: null }] })),
      entry("b", null)] as never} />);
    expect(screen.getByText(/1 of the sources in this scope carry a notice/)).toBeTruthy();
    expect(screen.getByText("T a")).toBeTruthy();
  });
});
