// F9 (§8.5): `Tracker` renders one block per `source_tracker` entry, in server
// order, with the server tooltip verbatim; a `not_obtained` 403 entry's tooltip
// contains "not proof of a paywall". The fixtures are the committed overview
// payloads the API serves (the unbound r2 round carries the 403 entry).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SourceTracker, { type TrackerEntry } from "@/components/SourceTracker";
import overview from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/overview.json";
import unboundOverview from "./fixtures/projects/example-news-and-returns/unbound/r2/overview.json";

const BLOCK_COLORS: Record<string, string> = {
  confirmed: "bg-emerald-500",
  awaiting_normalize: "bg-blue-500",
  not_a_document: "bg-amber-400",
  not_obtained: "bg-rose-500",
  not_attempted: "bg-gray-300",
  unclassified: "bg-slate-400",
};

function renderedStates(container: HTMLElement, entries: { state: string }[]): string[] {
  const tracker = container.querySelector('div[aria-label^="sources in this scope"]')!;
  const colourClasses = Object.values(BLOCK_COLORS);
  return [...tracker.querySelectorAll("div")]
    .filter((el) => colourClasses.some((cls) => el.classList.contains(cls)))
    .map((el) =>
      Object.entries(BLOCK_COLORS)
        .filter(([, cls]) => el.classList.contains(cls))
        .map(([state]) => state)[0],
    )
    .slice(0, entries.length);
}

describe("F9: SourceTracker — one block per candidate, server order, tooltip verbatim", () => {
  it("renders one block per entry, in server order", () => {
    for (const payload of [overview, unboundOverview]) {
      const entries = payload.source_tracker as unknown as TrackerEntry[];
      const { container } = render(<SourceTracker entries={entries} />);
      expect(renderedStates(container, entries)).toEqual(entries.map((e) => e.state));
    }
  });

  it("shows the server's tooltip verbatim, on click", async () => {
    const entries = unboundOverview.source_tracker as unknown as TrackerEntry[];
    const { container } = render(<SourceTracker entries={entries} />);
    const blocks = container.querySelectorAll('div[aria-label^="sources in this scope"] .overflow-hidden');
    fireEvent.click(blocks[0]);
    await waitFor(() => expect(screen.getByText(entries[0].tooltip)).toBeTruthy());
  });

  it("a not_obtained 403 entry's tooltip contains the F19 sentence", async () => {
    const entries = unboundOverview.source_tracker as unknown as TrackerEntry[];
    const refused = entries.find((e) => e.state === "not_obtained")!;
    expect(refused.tooltip).toContain("not proof of a paywall");
    const { container } = render(<SourceTracker entries={entries} />);
    const blocks = container.querySelectorAll('div[aria-label^="sources in this scope"] .overflow-hidden');
    fireEvent.click(blocks[entries.indexOf(refused)]);
    await waitFor(() => expect(screen.getByText(refused.tooltip)).toBeTruthy());
  });

  it("renders the state words with their counts in the legend", () => {
    const entries = unboundOverview.source_tracker as unknown as TrackerEntry[];
    const { container } = render(<SourceTracker entries={entries} />);
    const text = container.textContent!;
    expect(text).toContain("not_attempted 1");
    expect(text).toContain("not_obtained 1");
  });
});
