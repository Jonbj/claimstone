// J2: the journey renders the server's steps; the browser maps status to colour only.
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { NeedsYou, RunningNote, TheQuestions, TheTopic } from "@/components/JourneySide";
import JourneySteps from "@/components/JourneySteps";
import type { Journey } from "@/components/JourneySteps";
import flowOverview from "./fixtures/projects/example-news-and-returns/flows/0df548e3743689e1a0dd099da697aee4842e8a573f1225a8da13fec128a248cd/overview.json";

const journey = flowOverview.journey as unknown as Journey;
const rows = flowOverview.questions.rows as never;

function mount(j: Journey, writable = true, r = rows) {
  render(<MemoryRouter><JourneySteps journey={j} rows={r} base="/p/demo/f/sel1" writable={writable} /></MemoryRouter>);
}

describe("J2: JourneySteps", () => {
  afterEach(cleanup);

  it("renders steps in server order with status word and summary verbatim", () => {
    mount(journey);
    const items = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-step"));
    expect(items.map((li) => li.getAttribute("data-step"))).toEqual(journey.steps.map((s) => s.key));
    journey.steps.forEach((step, i) => {
      expect(items[i].getAttribute("data-status")).toBe(step.status);
      expect(within(items[i]).getByText(step.summary)).toBeTruthy();
      expect(items[i].querySelector("[data-status-word]")?.textContent).toBe(step.status.replace(/_/g, " "));
    });
  });

  it("never re-labels: the status and summary are shown as the server sent them", () => {
    const odd: Journey = { ...journey, steps: [{ ...journey.steps[0], status: "blocked", summary: "X is wrong." }] };
    mount(odd);
    expect(screen.getByText("X is wrong.")).toBeTruthy();
    expect(screen.getByText("blocked")).toBeTruthy();
    expect(screen.queryByText("running")).toBeNull();
  });

  it("an unknown figure renders an em dash, not 0", () => {
    mount(journey);
    const annotate = document.querySelector('[data-step="annotate"] [data-figure="rejected"] dd');
    expect(annotate?.textContent).toBe("—");
  });

  it("step 3 states the floor from the server's status", () => {
    mount(journey);
    expect(document.querySelector("[data-floor]")?.textContent).toBe("floor met · 1 ≥ 0.8");
  });

  it("J3.1: no floor line while the step is not started or nothing was found", () => {
    const copies = journey.steps.find((st) => st.key === "copies")!;
    const none: Journey = { ...journey, steps: [{ ...copies, status: "not_started", figures: { ...copies.figures, found: 0, rate: null, status: "INSUFFICIENT_ACQUISITION" } }] };
    mount(none);
    expect(document.querySelector("[data-floor]")).toBeNull();
    cleanup();
    mount({ ...journey, steps: [{ ...copies, status: "partial", figures: { ...copies.figures, found: 0 } }] });
    expect(document.querySelector("[data-floor]")).toBeNull();
  });

  it("Read and sign buttons only for matrix rows awaiting a person, linking to the desk", () => {
    const marked = (rows as { id: string; display_state: string }[]).map((r, i) =>
      i === 1 || i === 3 ? { ...r, display_state: "awaiting_a_person" } : r);
    mount(journey, true, marked as never);
    const expected = marked.filter((r) => r.display_state === "awaiting_a_person");
    expect(expected).toHaveLength(2);
    const links = screen.queryAllByRole("link", { name: /^Read and sign / });
    expect(links.map((l) => l.textContent)).toEqual(expected.map((r) => `Read and sign ${r.id}`));
    links.forEach((l, i) => expect(l.getAttribute("href")).toBe(`/p/demo/f/sel1/q/${expected[i].id}`));
  });

  it("legacy selectors show no write controls", () => {
    mount(journey, false);
    expect(screen.queryAllByRole("link", { name: /Read and sign/ })).toHaveLength(0);
  });
});

describe("J2: side column", () => {
  afterEach(cleanup);

  it("null needs_you renders the note, not zeros", () => {
    const needs = { required: null, optional: null, ready_to_sign: 0, note: "decisions belong to a bound flow" };
    render(<MemoryRouter><NeedsYou needs={needs} base="/p/d/u/x" writable={false} /></MemoryRouter>);
    expect(screen.getByText("decisions belong to a bound flow")).toBeTruthy();
    expect(screen.queryByText("Required decisions")).toBeNull();
    expect(screen.queryByRole("link", { name: /decisions/i })).toBeNull();
  });

  it("known counts link to Decisions", () => {
    render(<MemoryRouter><NeedsYou needs={journey.needs_you} base="/p/d/f/s" writable /></MemoryRouter>);
    expect(screen.getByText("Required decisions")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open decisions" }).getAttribute("href")).toBe("/p/d/f/s/decisions");
  });

  it("running null shows the named note; a list shows nothing here", () => {
    const { container, rerender } = render(<RunningNote journey={{ ...journey, running: null, running_note: "operations ledger damaged" }} />);
    expect(screen.getByText("operations ledger damaged")).toBeTruthy();
    rerender(<RunningNote journey={journey} />);
    expect(container.textContent).toBe("");
  });

  it("topics with terms and questions with state chips", () => {
    render(<MemoryRouter><TheTopic topics={journey.topics} /><TheQuestions rows={rows} base="/p/d/f/s" /></MemoryRouter>);
    expect(screen.getByText(journey.topics[0].label)).toBeTruthy();
    expect(document.querySelectorAll("[data-question-id]").length).toBe((rows as unknown[]).length);
  });
});
