// J2: the journey renders the server's steps; the browser maps status to colour only.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

  it("J3.2: figures drop status and empty drifted_parts, keep numbers, note is a muted sentence", () => {
    mount(journey);
    const copies = document.querySelector('[data-step="copies"]')!;
    expect(copies.querySelector('[data-figure="status"]')).toBeNull();
    expect(copies.querySelector('[data-figure="found"] dd')?.textContent).toBe("2");
    expect(copies.querySelector('[data-figure="rate"] dd')?.textContent).toBe("1");
    expect(document.querySelector('[data-step="protocol"] [data-figure="drifted_parts"]')).toBeNull();
    expect(document.querySelector('[data-step="search"] [data-figure="note"]')).toBeNull();
    expect(document.querySelector('[data-step="search"] [data-note]')?.textContent)
      .toBe("single channel (keyword): completeness not estimable");
    expect(document.querySelector('[data-step="annotate"] [data-figure="rejected"] dd')?.textContent).toBe("—");
  });

  it("J3.2: a non-empty drifted_parts is still shown", () => {
    const proto = journey.steps[0];
    mount({ ...journey, steps: [{ ...proto, figures: { ...proto.figures, drifted_parts: ["questions", "sources"] } }] });
    expect(document.querySelector('[data-figure="drifted_parts"] dd')?.textContent).toBe("questions, sources");
  });

  it("J3.3: an ISO figure shows as a UTC date-time with the raw value as title", () => {
    mount(journey);
    const dd = document.querySelector('[data-figure="bound_at"] dd');
    expect(dd?.textContent).toBe("6 Oct 2026, 00:00 UTC");
    expect(dd?.getAttribute("title")).toBe("2026-10-06T00:00:00+00:00");
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
  it("shows only the steps named in `keys`, with a chosen heading and no bar", () => {
    render(
      <MemoryRouter>
        <JourneySteps journey={journey} rows={rows} base="/p/demo/f/sel1" writable
                      keys={["copies", "documents"]} heading="Pipeline" bar={false} />
      </MemoryRouter>,
    );
    const shown = Array.from(document.querySelectorAll("[data-step]")).map((n) => n.getAttribute("data-step"));
    expect(shown).toEqual(["copies", "documents"]);
    expect(screen.getByRole("heading", { name: "Pipeline" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "The journey" })).toBeNull();
    expect(screen.queryByLabelText("Journey progress")).toBeNull();
  });

  it("a null heading renders no heading at all", () => {
    render(
      <MemoryRouter>
        <JourneySteps journey={journey} rows={rows} base="/p/demo/f/sel1" writable
                      keys={["protocol"]} heading={null} bar={false} />
      </MemoryRouter>,
    );
    expect(document.querySelector("section h2")).toBeNull();
    expect(document.querySelectorAll("[data-step]")).toHaveLength(1);
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

  it("J3.4: a no_profile row shows the human word, the code is the title", () => {
    const row = { ...(rows as Record<string, unknown>[])[0], id: "Q99", display_state: "no_profile", verdict: null, operational_not_applicable: false };
    render(<MemoryRouter><TheQuestions rows={[row] as never} base="/p/d/f/s" /></MemoryRouter>);
    const li = document.querySelector('[data-question-id="Q99"]')!;
    expect(within(li as HTMLElement).getByText("no profile yet").getAttribute("title")).toBe("no_profile");
    expect(within(li as HTMLElement).queryByText("no_profile")).toBeNull();
  });

  it("J3.5: first four topics with terms, the rest behind a toggle", () => {
    const many = Array.from({ length: 6 }, (_, i) => ({ id: `t${i}`, label: `Topic ${i}`, terms: [`term${i}a`, `term${i}b`] }));
    render(<TheTopic topics={many as never} />);
    expect(document.querySelectorAll("[data-topic]").length).toBe(4);
    expect(screen.getByText("term0a · term0b")).toBeTruthy();
    expect(screen.queryByText("Topic 4")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show all 6 topics" }));
    expect(document.querySelectorAll("[data-topic]").length).toBe(6);
    expect(screen.getByText("term5a · term5b")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show fewer topics" }));
    expect(document.querySelectorAll("[data-topic]").length).toBe(4);
  });

  it("J3.5: four or fewer topics have no toggle", () => {
    render(<TheTopic topics={journey.topics.slice(0, 4)} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("topics with terms and questions with state chips", () => {
    render(<MemoryRouter><TheTopic topics={journey.topics} /><TheQuestions rows={rows} base="/p/d/f/s" /></MemoryRouter>);
    expect(screen.getByText(journey.topics[0].label)).toBeTruthy();
    expect(document.querySelectorAll("[data-question-id]").length).toBe((rows as unknown[]).length);
  });
});
